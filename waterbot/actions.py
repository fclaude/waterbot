"""Shared action execution for WaterBot."""

import subprocess  # nosec B404
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import policy as policy_model
from . import scheduler
from .agent.memory import AgentMemory
from .config import AGENT_REQUIRE_CONFIRMATION
from .gpio import handler as gpio_handler
from .weather import WeatherContextProvider


@dataclass
class ActionResult:
    """Result returned by the shared action engine."""

    status: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    confirmation_token: Optional[str] = None

    @property
    def success(self) -> bool:
        """Return True when the action succeeded."""
        return self.status == "success"


class ActionEngine:
    """Validate, optionally confirm, execute, and audit WaterBot actions."""

    risky_actions = {
        "all_on",
        "all_off",
        "turn_all_on",
        "turn_all_off",
        "replace_device_schedule",
        "clear_device_schedule",
        "upsert_policy_schedule",
        "create_every_n_days_cycle",
        "remove_policy_schedule",
        "policy_remove",
    }

    def __init__(
        self,
        memory: Optional[AgentMemory] = None,
        weather_provider: Optional[WeatherContextProvider] = None,
    ) -> None:
        """Initialize the action engine."""
        self.memory = memory or AgentMemory()
        self.weather_provider = weather_provider or WeatherContextProvider()

    def preview_action(self, action_type: str, arguments: Dict[str, Any]) -> ActionResult:
        """Return a non-mutating description of an action."""
        description = self.describe_action(action_type, arguments)
        return ActionResult("preview", f"Preview: {description}", {"action_type": action_type, "arguments": arguments})

    def execute_action(
        self,
        action_type: str,
        arguments: Optional[Dict[str, Any]] = None,
        source: str = "command",
        channel_id: Optional[str] = None,
        require_confirmation: Optional[bool] = None,
        confirmed: bool = False,
    ) -> ActionResult:
        """Execute an action, requiring confirmation for risky agent actions."""
        args = arguments or {}
        normalized_type = _normalize_action_type(action_type)
        needs_confirmation = self._needs_confirmation(normalized_type, args, require_confirmation, confirmed)

        if needs_confirmation:
            description = self.describe_action(normalized_type, args)
            token = self.memory.create_confirmation(normalized_type, args, description, channel_id)
            message = (
                f"Confirmation required for: {description}\n"
                f"Reply `confirm {token}` to execute or `cancel {token}` to discard."
            )
            result = ActionResult("pending_confirmation", message, {"description": description}, token)
            self._record_event(normalized_type, args, result, source, channel_id)
            return result

        try:
            result = self._execute(normalized_type, args)
        except Exception as exc:
            result = ActionResult("error", f"Error executing {normalized_type}: {exc}")

        self._record_event(normalized_type, args, result, source, channel_id)
        return result

    def confirm(self, token: str, channel_id: Optional[str] = None, source: str = "confirmation") -> ActionResult:
        """Execute a pending confirmation token."""
        confirmation = self.memory.get_pending_confirmation(token, channel_id)
        if not confirmation:
            return ActionResult("not_found", f"No pending confirmation found for `{token}`.")

        result = self.execute_action(
            confirmation["action_type"],
            confirmation["arguments"],
            source=source,
            channel_id=confirmation.get("channel_id"),
            require_confirmation=False,
            confirmed=True,
        )
        self.memory.resolve_confirmation(token, "confirmed" if result.success else "failed")
        return result

    def cancel(self, token: str, channel_id: Optional[str] = None) -> ActionResult:
        """Cancel a pending confirmation token."""
        confirmation = self.memory.get_pending_confirmation(token, channel_id)
        if not confirmation:
            return ActionResult("not_found", f"No pending confirmation found for `{token}`.")
        self.memory.resolve_confirmation(token, "cancelled")
        return ActionResult("cancelled", f"Cancelled pending action `{token}`.")

    def describe_action(self, action_type: str, arguments: Dict[str, Any]) -> str:
        """Return a concise human-readable action description."""
        action_type = _normalize_action_type(action_type)
        if action_type == "turn_device_on":
            device = arguments.get("device", "unknown")
            duration = arguments.get("duration_minutes")
            return f"turn {device} on" + (f" for {duration} minutes" if duration else "")
        if action_type == "turn_device_off":
            return f"turn {arguments.get('device', 'unknown')} off"
        if action_type == "all_on":
            return "turn all devices on"
        if action_type == "all_off":
            return "turn all devices off"
        if action_type == "replace_device_schedule":
            return f"replace all schedules for {arguments.get('device', 'unknown')}"
        if action_type == "clear_device_schedule":
            return f"clear all schedules for {arguments.get('device', 'unknown')}"
        if action_type == "upsert_policy_schedule":
            policy = arguments.get("policy", {})
            return f"save flexible policy {policy.get('id', 'new policy')}"
        if action_type == "create_every_n_days_cycle":
            return (
                f"create cycle for {arguments.get('device', 'unknown')} every "
                f"{arguments.get('every')} days at {arguments.get('at')}"
            )
        if action_type in {"remove_policy_schedule", "policy_remove"}:
            return f"remove flexible policy {arguments.get('policy_id', 'unknown')}"
        return action_type.replace("_", " ")

    def _needs_confirmation(
        self,
        action_type: str,
        arguments: Dict[str, Any],
        require_confirmation: Optional[bool],
        confirmed: bool,
    ) -> bool:
        if confirmed:
            return False
        if require_confirmation is False:
            return False
        if require_confirmation is True:
            return action_type in self.risky_actions or _is_all_device_action(action_type, arguments)
        return AGENT_REQUIRE_CONFIRMATION and (
            action_type in self.risky_actions or _is_all_device_action(action_type, arguments)
        )

    def _execute(self, action_type: str, arguments: Dict[str, Any]) -> ActionResult:
        if action_type == "get_device_status":
            return _status_result(arguments.get("device"))
        if action_type == "turn_device_on":
            return _turn_device_on(arguments)
        if action_type == "turn_device_off":
            return _turn_device_off(arguments)
        if action_type == "all_on":
            timeout = arguments.get("timeout")
            gpio_handler.turn_all_on(timeout)
            message = "All devices turned ON"
            if timeout:
                message += f" for {int(timeout) // 60} minutes"
            return ActionResult("success", message)
        if action_type == "all_off":
            timeout = arguments.get("timeout")
            gpio_handler.turn_all_off(timeout)
            message = "All devices turned OFF"
            if timeout:
                message += f" for {int(timeout) // 60} minutes"
            return ActionResult("success", message)
        if action_type == "add_schedule":
            return _add_schedule(arguments)
        if action_type == "remove_schedule":
            return _remove_schedule(arguments)
        if action_type == "replace_device_schedule":
            return _replace_device_schedule(arguments)
        if action_type == "clear_device_schedule":
            return _clear_device_schedule(arguments)
        if action_type == "get_schedules":
            return _schedules_result(arguments.get("device"))
        if action_type == "upsert_policy_schedule":
            saved_policy = scheduler.upsert_policy_schedule(arguments["policy"])
            return ActionResult("success", f"Saved flexible schedule:\n{policy_model.policy_summary(saved_policy)}")
        if action_type == "create_every_n_days_cycle":
            policy_data = policy_model.create_every_n_days_policy(
                device=arguments["device"],
                every=int(arguments["every"]),
                at=arguments["at"],
                duration_minutes=float(arguments["duration_minutes"]),
                anchor_date=arguments.get("anchor_date"),
            )
            saved_policy = scheduler.upsert_policy_schedule(policy_data)
            return ActionResult("success", f"Saved flexible cycle:\n{policy_model.policy_summary(saved_policy)}")
        if action_type in {"remove_policy_schedule", "policy_remove"}:
            policy_id = arguments["policy_id"]
            if scheduler.remove_policy_schedule(policy_id):
                return ActionResult("success", f"Removed flexible schedule: {policy_id}")
            return ActionResult("failed", f"No such flexible schedule found: {policy_id}")
        if action_type == "get_policy_schedules":
            return _policy_schedules_result()
        if action_type == "get_weather_context":
            return _weather_result(self.weather_provider)
        if action_type == "get_current_time":
            return _time_result()
        if action_type == "get_ip_addresses":
            return _ip_result()
        if action_type == "test_notification":
            scheduler_instance = scheduler.get_scheduler()
            scheduler_instance._send_discord_notification("test_device", "on", True)
            return ActionResult("success", "Test notification sent via scheduler system")
        if action_type == "get_policy_decision_history":
            return _policy_decision_history_result(self.memory, arguments.get("device"))
        if action_type == "record_user_feedback":
            feedback = str(arguments["feedback"])
            self.memory.record_feedback(feedback, arguments.get("channel_id"), arguments.get("device"))
            return ActionResult("success", "Recorded feedback for future watering decisions.")

        return ActionResult("failed", f"Unknown action: {action_type}")

    def _record_event(
        self,
        action_type: str,
        arguments: Dict[str, Any],
        result: ActionResult,
        source: str,
        channel_id: Optional[str],
    ) -> None:
        self.memory.record_action_event(
            action_type=action_type,
            arguments=arguments,
            status=result.status,
            message=result.message,
            source=source,
            channel_id=channel_id,
            confirmation_token=result.confirmation_token,
        )


def _normalize_action_type(action_type: str) -> str:
    aliases = {
        "status": "get_device_status",
        "device_on": "turn_device_on",
        "device_off": "turn_device_off",
        "all_on": "all_on",
        "all_off": "all_off",
        "schedule_add": "add_schedule",
        "schedule_remove": "remove_schedule",
        "show_schedules": "get_schedules",
        "show_device_schedules": "get_schedules",
        "show_policy_schedules": "get_policy_schedules",
        "policy_add_every_n_days": "create_every_n_days_cycle",
        "policy_remove": "remove_policy_schedule",
        "why": "get_policy_decision_history",
        "feedback": "record_user_feedback",
        "time": "get_current_time",
        "ip": "get_ip_addresses",
        "test": "test_notification",
    }
    return aliases.get(action_type, action_type)


def _is_all_device_action(action_type: str, arguments: Dict[str, Any]) -> bool:
    device = str(arguments.get("device", "")).lower()
    return action_type in {"all_on", "all_off"} or device == "all"


def _status_result(device: Optional[str] = None) -> ActionResult:
    status = gpio_handler.get_status()
    if not status:
        return ActionResult("success", "No devices configured")
    if device:
        key = device.lower()
        if key not in status:
            return ActionResult("failed", f"Device '{device}' not found")
        return ActionResult("success", f"Device '{device}' is {'ON' if status[key] else 'OFF'}")

    lines = ["Device Status:"]
    lines.extend(f"- {dev}: {'ON' if is_on else 'OFF'}" for dev, is_on in status.items())
    return ActionResult("success", "\n".join(lines))


def _turn_device_on(arguments: Dict[str, Any]) -> ActionResult:
    device = str(arguments["device"])
    duration = arguments.get("duration_minutes")
    timeout = int(float(duration) * 60) if duration else arguments.get("timeout")
    if device.lower() == "all":
        gpio_handler.turn_all_on(timeout)
        return ActionResult("success", "All devices turned ON")
    if gpio_handler.turn_on(device, timeout):
        message = f"Device '{device}' turned ON"
        if duration:
            message += f" for {duration} minutes"
        elif timeout:
            message += f" for {int(timeout) // 60} minutes"
        return ActionResult("success", message)
    return ActionResult("failed", f"Error: Unknown device '{device}'")


def _turn_device_off(arguments: Dict[str, Any]) -> ActionResult:
    device = str(arguments["device"])
    duration = arguments.get("duration_minutes")
    timeout = int(float(duration) * 60) if duration else arguments.get("timeout")
    if device.lower() == "all":
        gpio_handler.turn_all_off(timeout)
        return ActionResult("success", "All devices turned OFF")
    if gpio_handler.turn_off(device, timeout):
        message = f"Device '{device}' turned OFF"
        if duration:
            message += f" for {duration} minutes"
        elif timeout:
            message += f" for {int(timeout) // 60} minutes"
        return ActionResult("success", message)
    return ActionResult("failed", f"Error: Unknown device '{device}'")


def _add_schedule(arguments: Dict[str, Any]) -> ActionResult:
    device = arguments["device"]
    action = arguments["action"]
    time_str = arguments["time"]
    if scheduler.add_schedule(device, action, time_str):
        return ActionResult("success", f"Added schedule: {device} {action} at {time_str}")
    return ActionResult("failed", f"Failed to add schedule for {device}")


def _remove_schedule(arguments: Dict[str, Any]) -> ActionResult:
    device = arguments["device"]
    action = arguments["action"]
    time_str = arguments["time"]
    if scheduler.remove_schedule(device, action, time_str):
        return ActionResult("success", f"Removed schedule: {device} {action} at {time_str}")
    return ActionResult("failed", f"No such schedule found: {device} {action} at {time_str}")


def _replace_device_schedule(arguments: Dict[str, Any]) -> ActionResult:
    device = arguments["device"]
    periods = arguments["schedule_periods"]
    from .config import get_schedules

    existing = get_schedules(device)
    removed_count = sum(len(times) for times in existing.values())
    replacement: Dict[str, List[str]] = {"on": [], "off": []}
    for period in periods:
        replacement["on"].append(period["start_time"])
        replacement["off"].append(period["end_time"])
    if not scheduler.replace_device_schedules(device, replacement):
        return ActionResult("failed", f"Failed to replace schedule for '{device}'")

    added_count = len(replacement["on"]) + len(replacement["off"])
    lines = [
        f"Schedule replacement for '{device}' completed:",
        f"- Removed {removed_count} existing schedules",
        f"- Added {added_count} new schedules",
        "",
        f"New schedule for {device}:",
    ]
    for index, period in enumerate(periods, 1):
        lines.append(f"  Period {index}: {period['start_time']} to {period['end_time']}")
    return ActionResult("success", "\n".join(lines))


def _clear_device_schedule(arguments: Dict[str, Any]) -> ActionResult:
    device = arguments["device"]
    from .config import get_schedules

    existing = get_schedules(device)
    removed_count = 0
    for action in ["on", "off"]:
        for time_str in existing.get(action, [])[:]:
            if scheduler.remove_schedule(device, action, time_str):
                removed_count += 1
    return ActionResult("success", f"Cleared all schedules for '{device}' - removed {removed_count} schedule entries")


def _schedules_result(device: Optional[str] = None) -> ActionResult:
    from .config import get_schedules

    schedules = get_schedules(device)
    if not schedules:
        if device:
            return ActionResult("success", f"No schedules configured for device '{device}'")
        return ActionResult("success", "No schedules configured")

    lines = ["Device Schedules:"]
    if device:
        lines.append(f"{device.upper()}:")
        for action, times in schedules.items():
            lines.extend(f"  {action.upper()} at {time_str}" for time_str in times)
    else:
        for dev, actions in schedules.items():
            lines.append(f"{dev.upper()}:")
            for action, times in actions.items():
                lines.extend(f"  {action.upper()} at {time_str}" for time_str in times)

    next_runs = scheduler.get_next_runs()
    if next_runs:
        lines.extend(["", "Next scheduled runs:"])
        lines.extend(
            f"  {run['device']} {run['action']} at {run['time']} (next: {run['next_run']})" for run in next_runs[:5]
        )
    return ActionResult("success", "\n".join(lines))


def _policy_schedules_result() -> ActionResult:
    policies = scheduler.get_policy_schedules()
    if not policies:
        return ActionResult("success", "No flexible policy schedules configured")
    lines = ["Flexible Policy Schedules:"]
    lines.extend(f"- {policy_model.policy_summary(saved_policy)}" for saved_policy in policies)
    return ActionResult("success", "\n".join(lines))


def _weather_result(provider: WeatherContextProvider) -> ActionResult:
    context = provider.get_context()
    if not context:
        return ActionResult("success", "No weather context available")
    lines = ["Weather Context:"]
    lines.extend(f"- {key}: {value}" for key, value in sorted(context.items()))
    return ActionResult("success", "\n".join(lines), {"context": context})


def _time_result() -> ActionResult:
    current_time = datetime.now()
    message = f"Current Time: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    try:
        tz_result = subprocess.run(  # nosec B603, B607
            ["timedatectl", "show", "--property=Timezone", "--value"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if tz_result.returncode == 0 and tz_result.stdout.strip():
            message += f"\nTimezone: {tz_result.stdout.strip()}"
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        try:
            message += f"\nTimezone: {time.tzname[time.daylight]}"
        except Exception:  # nosec B110
            pass
    return ActionResult("success", message)


def _ip_result() -> ActionResult:
    ip_info = {}
    try:
        net_result = subprocess.run(  # nosec B603, B607
            ["ls", "/sys/class/net/"],
            capture_output=True,
            text=True,
            check=True,
        )
        interfaces = [iface for iface in net_result.stdout.strip().split() if iface != "lo"]
        for interface in interfaces:
            try:
                ip_result = subprocess.run(  # nosec B603, B607
                    ["ip", "addr", "show", interface],
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except subprocess.CalledProcessError:
                continue
            for line in ip_result.stdout.split("\n"):
                if "inet " in line and "127.0.0.1" not in line:
                    ip = line.strip().split()[1].split("/")[0]
                    if ip:
                        ip_info[interface] = ip
                        break
    except subprocess.CalledProcessError:
        pass

    if not ip_info:
        return ActionResult("success", "No network interfaces found with IP addresses.")
    lines = ["SSH Access Information:"]
    lines.extend(f"- ssh pi@{ip} (via {interface})" for interface, ip in ip_info.items())
    return ActionResult("success", "\n".join(lines), {"ip_info": ip_info})


def _policy_decision_history_result(memory: AgentMemory, device: Optional[str] = None) -> ActionResult:
    decisions = memory.get_policy_decision_history(device, limit=5)
    if not decisions:
        target = f" for {device}" if device else ""
        return ActionResult("success", f"No policy decision history found{target}.")

    lines = ["Recent policy decisions:"]
    for decision in decisions:
        status = "skipped" if decision["skipped"] else "ran" if decision["executed"] else "failed"
        rules = ", ".join(decision["matched_rules"]) or "no rules matched"
        lines.append(
            f"- {decision['created_at']}: {decision['device']} {status} "
            f"({decision['duration_minutes']} minutes, {rules}) - {decision['message']}"
        )
    return ActionResult("success", "\n".join(lines), {"decisions": decisions})
