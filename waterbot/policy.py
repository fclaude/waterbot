"""Flexible schedule policies for WaterBot."""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from tempfile import NamedTemporaryFile
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from .config import DEVICE_TO_PIN, POLICY_SCHEDULE_CONFIG_FILE
from .gpio import handler as gpio_handler
from .weather import WeatherContextProvider

logger = logging.getLogger("waterbot.policy")

WEEKDAYS = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}


@dataclass
class PolicyExecutionPlan:
    """The resolved action for a policy run."""

    policy_id: str
    device: str
    run_key: str
    should_run: bool
    duration_minutes: float
    matched_rules: List[str]
    reason: str


@dataclass
class PolicyRunResult:
    """Result from a due policy evaluation."""

    policy_id: str
    device: str
    run_key: str
    executed: bool
    skipped: bool
    duration_minutes: float
    message: str
    context: Dict[str, float] = field(default_factory=dict)
    matched_rules: List[str] = field(default_factory=list)


class PolicyValidationError(ValueError):
    """Raised when a policy is invalid."""


class PolicyScheduleStore:
    """Persist flexible schedule policies."""

    def __init__(self, path: str = POLICY_SCHEDULE_CONFIG_FILE) -> None:
        """Initialize the store."""
        self.path = path

    def list_policies(self) -> List[Dict[str, Any]]:
        """Load all policies."""
        return [self._normalize_policy(policy) for policy in self._read_policies()]

    def get_policy(self, policy_id: str) -> Optional[Dict[str, Any]]:
        """Get one policy by ID."""
        for policy in self.list_policies():
            if policy["id"] == policy_id:
                return policy
        return None

    def upsert_policy(self, policy: Dict[str, Any]) -> Dict[str, Any]:
        """Create or replace a policy."""
        normalized = self._normalize_policy(policy)
        policies = self._read_policies()
        replaced = False

        for index, existing in enumerate(policies):
            if existing.get("id") == normalized["id"]:
                existing_run_key = existing.get("last_run_key")
                if "last_run_key" not in normalized and existing_run_key:
                    normalized["last_run_key"] = existing_run_key
                policies[index] = normalized
                replaced = True
                break

        if not replaced:
            policies.append(normalized)

        self._write_policies(policies)
        return normalized

    def remove_policy(self, policy_id: str) -> bool:
        """Remove a policy by ID."""
        policies = self._read_policies()
        remaining = [policy for policy in policies if policy.get("id") != policy_id]
        if len(remaining) == len(policies):
            return False
        self._write_policies(remaining)
        return True

    def mark_run(self, policy_id: str, run_key: str) -> None:
        """Record that a policy has been evaluated for a scheduled run."""
        policies = self._read_policies()
        for policy in policies:
            if policy.get("id") == policy_id:
                policy["last_run_key"] = run_key
                policy["last_run_at"] = datetime.now().isoformat(timespec="seconds")
                self._write_policies(policies)
                return

    def _read_policies(self) -> List[Dict[str, Any]]:
        """Read policy data from disk."""
        if not os.path.exists(self.path):
            return []

        try:
            with open(self.path, "r") as file_handle:
                payload = json.load(file_handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load policy schedule file '%s': %s", self.path, exc)
            return []

        if isinstance(payload, list):
            return [policy for policy in payload if isinstance(policy, dict)]
        if isinstance(payload, dict):
            policies = payload.get("policies", [])
            if isinstance(policies, list):
                return [policy for policy in policies if isinstance(policy, dict)]

        logger.warning("Policy schedule file '%s' has an unsupported format", self.path)
        return []

    def _write_policies(self, policies: List[Dict[str, Any]]) -> None:
        """Write policies atomically."""
        directory = os.path.dirname(os.path.abspath(self.path)) or "."
        os.makedirs(directory, exist_ok=True)
        payload = {"version": 1, "policies": policies}

        with NamedTemporaryFile("w", delete=False, dir=directory) as temp_file:
            json.dump(payload, temp_file, indent=2)
            temp_file.write("\n")
            temp_path = temp_file.name

        os.replace(temp_path, self.path)

    def _normalize_policy(self, policy: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and fill defaults for one policy."""
        normalized = dict(policy)
        normalized["id"] = _policy_id(normalized)
        normalized["device"] = _required_string(normalized, "device").lower()
        normalized["enabled"] = bool(normalized.get("enabled", True))
        normalized["action"] = normalized.get("action", "water")

        if normalized["device"] not in DEVICE_TO_PIN:
            raise PolicyValidationError(f"Unknown device '{normalized['device']}'")

        normalized["recurrence"] = _normalize_recurrence(normalized.get("recurrence"))
        normalized["duration"] = _normalize_duration(normalized.get("duration"))
        normalized["rules"] = _normalize_rules(normalized.get("rules", []))

        return normalized


class PolicyScheduler:
    """Evaluate and execute flexible schedule policies."""

    def __init__(
        self,
        store: Optional[PolicyScheduleStore] = None,
        weather_provider: Optional[WeatherContextProvider] = None,
    ) -> None:
        """Initialize the scheduler."""
        self.store = store or PolicyScheduleStore()
        self.weather_provider = weather_provider or WeatherContextProvider()

    def run_due(self, now: Optional[datetime] = None) -> List[PolicyRunResult]:
        """Evaluate and execute all policies currently due."""
        current_time = now or datetime.now()
        results: List[PolicyRunResult] = []

        try:
            policies = self.store.list_policies()
        except PolicyValidationError as exc:
            logger.error("Invalid policy schedule configuration: %s", exc)
            return []

        due_policies = []
        for policy in policies:
            if not policy.get("enabled", True):
                continue

            run_key = get_due_run_key(policy, current_time)
            if not run_key or policy.get("last_run_key") == run_key:
                continue
            due_policies.append((policy, run_key))

        if not due_policies:
            return []

        context = self.weather_provider.get_context()
        for policy, run_key in due_policies:
            plan = evaluate_policy(policy, context, run_key)
            result = self._execute_plan(plan)
            result.context = dict(context)
            result.matched_rules = list(plan.matched_rules)
            self.store.mark_run(policy["id"], run_key)
            results.append(result)

        return results

    def _execute_plan(self, plan: PolicyExecutionPlan) -> PolicyRunResult:
        """Execute a resolved policy plan."""
        if not plan.should_run:
            message = f"Policy '{plan.policy_id}' skipped {plan.device}: {plan.reason}"
            logger.info(message)
            return PolicyRunResult(
                policy_id=plan.policy_id,
                device=plan.device,
                run_key=plan.run_key,
                executed=False,
                skipped=True,
                duration_minutes=0,
                message=message,
            )

        timeout_seconds = max(1, int(round(plan.duration_minutes * 60)))
        success = gpio_handler.turn_on(plan.device, timeout_seconds)
        if success:
            message = (
                f"Policy '{plan.policy_id}' ran {plan.device} for "
                f"{_format_minutes(plan.duration_minutes)}"
            )
            if plan.matched_rules:
                message += f" ({', '.join(plan.matched_rules)})"
        else:
            message = f"Policy '{plan.policy_id}' failed: unknown device '{plan.device}'"

        logger.info(message)
        return PolicyRunResult(
            policy_id=plan.policy_id,
            device=plan.device,
            run_key=plan.run_key,
            executed=success,
            skipped=False,
            duration_minutes=plan.duration_minutes if success else 0,
            message=message,
        )


def list_policies() -> List[Dict[str, Any]]:
    """List flexible schedule policies from the default store."""
    return PolicyScheduleStore().list_policies()


def upsert_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    """Create or replace a flexible schedule policy in the default store."""
    return PolicyScheduleStore().upsert_policy(policy)


def remove_policy(policy_id: str) -> bool:
    """Remove a flexible schedule policy from the default store."""
    return PolicyScheduleStore().remove_policy(policy_id)


def get_next_policy_runs(now: Optional[datetime] = None, horizon_days: int = 370) -> List[Dict[str, str]]:
    """Return next run information for flexible policies."""
    current_time = now or datetime.now()
    runs = []
    for saved_policy in list_policies():
        next_run = get_next_run(saved_policy, current_time, horizon_days)
        if next_run:
            runs.append(
                {
                    "id": saved_policy["id"],
                    "device": saved_policy["device"],
                    "next_run": next_run.isoformat(timespec="minutes"),
                }
            )
    runs.sort(key=lambda item: item["next_run"])
    return runs


def get_next_run(policy: Dict[str, Any], now: Optional[datetime] = None, horizon_days: int = 370) -> Optional[datetime]:
    """Find the next scheduled run for a policy."""
    current_time = now or datetime.now()
    recurrence = policy["recurrence"]
    run_time = _parse_hhmm(recurrence["at"])

    for day_offset in range(horizon_days + 1):
        candidate_date = current_time.date() + timedelta(days=day_offset)
        if not _date_matches_recurrence(recurrence, candidate_date):
            continue
        if not _date_matches_active_window(recurrence, candidate_date):
            continue

        candidate = datetime.combine(candidate_date, run_time)
        if candidate > current_time:
            return candidate

    return None


def get_due_run_key(policy: Dict[str, Any], now: datetime) -> Optional[str]:
    """Return the due run key for a policy, if it should run now."""
    recurrence = policy["recurrence"]
    run_time = _parse_hhmm(recurrence["at"])
    scheduled_at = datetime.combine(now.date(), run_time)
    grace_minutes = int(recurrence.get("missed_grace_minutes", 2))

    if now < scheduled_at or now > scheduled_at + timedelta(minutes=grace_minutes):
        return None
    if not _date_matches_recurrence(recurrence, now.date()):
        return None
    if not _date_matches_active_window(recurrence, now.date()):
        return None

    return scheduled_at.isoformat(timespec="minutes")


def evaluate_policy(policy: Dict[str, Any], context: Dict[str, float], run_key: str) -> PolicyExecutionPlan:
    """Resolve duration and skip decisions for a policy."""
    duration_config = policy["duration"]
    duration_minutes = float(duration_config["base_minutes"])
    matched_rules: List[str] = []

    for index, rule in enumerate(policy.get("rules", []), 1):
        if not _conditions_match(rule.get("when", {}), context):
            continue

        rule_name = str(rule.get("name") or f"rule {index}")
        matched_rules.append(rule_name)
        effect = rule.get("then", {})

        if effect.get("skip"):
            return PolicyExecutionPlan(
                policy_id=policy["id"],
                device=policy["device"],
                run_key=run_key,
                should_run=False,
                duration_minutes=0,
                matched_rules=matched_rules,
                reason=rule_name,
            )

        if "duration_minutes" in effect:
            duration_minutes = float(effect["duration_minutes"])
        if "duration_multiplier" in effect:
            duration_minutes *= float(effect["duration_multiplier"])
        if "duration_delta_minutes" in effect:
            duration_minutes += float(effect["duration_delta_minutes"])

    duration_minutes = max(float(duration_config["min_minutes"]), duration_minutes)
    duration_minutes = min(float(duration_config["max_minutes"]), duration_minutes)

    return PolicyExecutionPlan(
        policy_id=policy["id"],
        device=policy["device"],
        run_key=run_key,
        should_run=True,
        duration_minutes=duration_minutes,
        matched_rules=matched_rules,
        reason="scheduled",
    )


def policy_summary(policy: Dict[str, Any]) -> str:
    """Return a compact human-readable policy summary."""
    recurrence = policy["recurrence"]
    duration = policy["duration"]
    rule_count = len(policy.get("rules", []))
    enabled = "enabled" if policy.get("enabled", True) else "disabled"
    recurrence_text = _recurrence_text(recurrence)
    return (
        f"{policy['id']}: {policy['device']} {recurrence_text} "
        f"for {_format_minutes(float(duration['base_minutes']))}; {rule_count} rules; {enabled}"
    )


def create_every_n_days_policy(
    device: str,
    every: int,
    at: str,
    duration_minutes: float,
    anchor_date: Optional[str] = None,
    policy_id: Optional[str] = None,
    rules: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a policy that runs every N days."""
    return {
        "id": policy_id or f"{device.lower()}-every-{every}-days-{at.replace(':', '')}",
        "device": device.lower(),
        "recurrence": {
            "type": "every_n_days",
            "every": every,
            "at": at,
            "anchor_date": anchor_date or date.today().isoformat(),
        },
        "duration": {
            "base_minutes": duration_minutes,
            "min_minutes": max(1, duration_minutes),
            "max_minutes": duration_minutes,
        },
        "rules": rules or [],
    }


def _policy_id(policy: Dict[str, Any]) -> str:
    raw_id = str(policy.get("id") or "").strip().lower()
    if raw_id:
        policy_id = re.sub(r"[^a-z0-9_.-]+", "-", raw_id).strip("-")
        if policy_id:
            return policy_id
    return f"policy-{uuid4().hex[:8]}"


def _required_string(data: Dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PolicyValidationError(f"Policy requires a non-empty '{key}'")
    return value.strip()


def _normalize_recurrence(recurrence: Any) -> Dict[str, Any]:
    if not isinstance(recurrence, dict):
        raise PolicyValidationError("Policy recurrence must be an object")

    normalized = dict(recurrence)
    recurrence_type = normalized.get("type")
    if recurrence_type not in {"daily", "every_n_days", "weekly"}:
        raise PolicyValidationError("Policy recurrence.type must be daily, every_n_days, or weekly")

    at = _required_string(normalized, "at")
    if not _valid_hhmm(at):
        raise PolicyValidationError("Policy recurrence.at must use HH:MM")
    normalized["at"] = at

    if recurrence_type == "every_n_days":
        every = int(normalized.get("every", 0))
        if every < 1:
            raise PolicyValidationError("every_n_days recurrence requires every >= 1")
        normalized["every"] = every
        anchor = str(normalized.get("anchor_date") or date.today().isoformat())
        _parse_date(anchor)
        normalized["anchor_date"] = anchor

    if recurrence_type == "weekly":
        days = normalized.get("days")
        if not isinstance(days, list) or not days:
            raise PolicyValidationError("weekly recurrence requires non-empty days")
        normalized["days"] = [_normalize_weekday(day_value) for day_value in days]

    if "active_between" in normalized:
        active_between = normalized["active_between"]
        if not isinstance(active_between, dict):
            raise PolicyValidationError("active_between must be an object")
        _parse_month_day(_required_string(active_between, "start"))
        _parse_month_day(_required_string(active_between, "end"))

    normalized["missed_grace_minutes"] = int(normalized.get("missed_grace_minutes", 2))
    return normalized


def _normalize_duration(duration: Any) -> Dict[str, float]:
    if not isinstance(duration, dict):
        raise PolicyValidationError("Policy duration must be an object")

    base = float(duration.get("base_minutes", 0))
    if base <= 0:
        raise PolicyValidationError("Policy duration.base_minutes must be > 0")

    min_minutes = float(duration.get("min_minutes", base))
    max_minutes = float(duration.get("max_minutes", base))
    if min_minutes < 0 or max_minutes <= 0 or min_minutes > max_minutes:
        raise PolicyValidationError("Policy duration bounds are invalid")

    return {
        "base_minutes": base,
        "min_minutes": min_minutes,
        "max_minutes": max_minutes,
    }


def _normalize_rules(rules: Any) -> List[Dict[str, Any]]:
    if not isinstance(rules, list):
        raise PolicyValidationError("Policy rules must be a list")

    normalized_rules = []
    for rule in rules:
        if not isinstance(rule, dict):
            raise PolicyValidationError("Each policy rule must be an object")
        if not isinstance(rule.get("when", {}), dict):
            raise PolicyValidationError("Policy rule.when must be an object")
        if not isinstance(rule.get("then", {}), dict):
            raise PolicyValidationError("Policy rule.then must be an object")
        for comparison in rule.get("when", {}).values():
            if isinstance(comparison, dict):
                for operator in comparison:
                    if operator not in {">", ">=", "<", "<=", "==", "!="}:
                        raise PolicyValidationError(f"Unsupported rule operator '{operator}'")
        normalized_rules.append(dict(rule))
    return normalized_rules


def _conditions_match(conditions: Dict[str, Any], context: Dict[str, float]) -> bool:
    for metric, comparison in conditions.items():
        if metric not in context:
            return False

        value = context[metric]
        if isinstance(comparison, dict):
            for operator, expected in comparison.items():
                if not _compare(float(value), operator, float(expected)):
                    return False
        elif float(value) != float(comparison):
            return False

    return True


def _compare(value: float, operator: str, expected: float) -> bool:
    operators: Dict[str, Callable[[float, float], bool]] = {
        ">": lambda left, right: left > right,
        ">=": lambda left, right: left >= right,
        "<": lambda left, right: left < right,
        "<=": lambda left, right: left <= right,
        "==": lambda left, right: left == right,
        "!=": lambda left, right: left != right,
    }
    if operator not in operators:
        raise PolicyValidationError(f"Unsupported rule operator '{operator}'")
    return operators[operator](value, expected)


def _date_matches_recurrence(recurrence: Dict[str, Any], run_date: date) -> bool:
    recurrence_type = recurrence["type"]
    if recurrence_type == "daily":
        return True

    if recurrence_type == "weekly":
        return run_date.weekday() in recurrence["days"]

    anchor = _parse_date(recurrence["anchor_date"])
    delta_days = (run_date - anchor).days
    return delta_days >= 0 and delta_days % int(recurrence["every"]) == 0


def _date_matches_active_window(recurrence: Dict[str, Any], run_date: date) -> bool:
    active_between = recurrence.get("active_between")
    if not active_between:
        return True

    start = _parse_month_day(active_between["start"])
    end = _parse_month_day(active_between["end"])
    current = (run_date.month, run_date.day)

    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def _recurrence_text(recurrence: Dict[str, Any]) -> str:
    if recurrence["type"] == "daily":
        return f"daily at {recurrence['at']}"
    if recurrence["type"] == "weekly":
        days = ", ".join(_weekday_name(day) for day in recurrence["days"])
        return f"weekly on {days} at {recurrence['at']}"
    return f"every {recurrence['every']} days at {recurrence['at']}"


def _format_minutes(minutes: float) -> str:
    if minutes == int(minutes):
        return f"{int(minutes)} minutes"
    return f"{minutes:.1f} minutes"


def _valid_hhmm(value: str) -> bool:
    if not re.match(r"^\d{2}:\d{2}$", value):
        return False
    hour, minute = value.split(":")
    return int(hour) <= 23 and int(minute) <= 59


def _parse_hhmm(value: str) -> time:
    if not _valid_hhmm(value):
        raise PolicyValidationError(f"Invalid HH:MM value '{value}'")
    hour, minute = value.split(":")
    return time(hour=int(hour), minute=int(minute))


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise PolicyValidationError(f"Invalid date '{value}', expected YYYY-MM-DD") from exc


def _parse_month_day(value: str) -> tuple:
    parts = value.split("-")
    if len(parts) != 2:
        raise PolicyValidationError(f"Invalid month-day '{value}', expected MM-DD")
    month, day = int(parts[0]), int(parts[1])
    if month < 1 or month > 12 or day < 1 or day > 31:
        raise PolicyValidationError(f"Invalid month-day '{value}'")
    return month, day


def _normalize_weekday(value: Any) -> int:
    if isinstance(value, int) and 0 <= value <= 6:
        return value
    if isinstance(value, str) and value.lower() in WEEKDAYS:
        return WEEKDAYS[value.lower()]
    raise PolicyValidationError(f"Invalid weekday '{value}'")


def _weekday_name(day: int) -> str:
    return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][day]
