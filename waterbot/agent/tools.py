"""Allowlisted OpenAI tool schemas for WaterBot."""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List

# Tools the model may call. IP lookup and test notifications stay as typed commands.
#
# preview_action/execute_action were dropped: every action_type they could dispatch
# is already reachable through its own typed tool below, and risky actions already
# surface a confirmation preview before executing - so the generic dispatchers only
# doubled the schema size sent on every LLM call without adding capability.
# turn_device_on/turn_device_off, add_schedule/remove_schedule, and
# confirm_pending_action/cancel_pending_action are collapsed into one tool each
# (set_device_power, edit_schedule, respond_to_pending_action) since each pair
# shared the same arguments and only varied by one enum value.
# replace_device_schedule was dropped in favor of clear_device_schedule + add_schedule,
# which the model can already issue together in a single round.
AGENT_TOOL_NAMES: FrozenSet[str] = frozenset(
    {
        "get_recent_context",
        "get_policy_decision_history",
        "record_user_feedback",
        "get_device_status",
        "set_device_power",
        "edit_schedule",
        "clear_device_schedule",
        "get_schedules",
        "upsert_policy_schedule",
        "create_every_n_days_cycle",
        "remove_policy_schedule",
        "get_policy_schedules",
        "get_weather_context",
        "get_current_time",
        "respond_to_pending_action",
    }
)

# Allowlist checked by AgentRuntime before dispatching a tool call to ActionEngine.
# all_on/all_off/replace_device_schedule have no dedicated tool anymore (superseded
# by set_device_power(device="all") and clear_device_schedule + add_schedule) but
# stay allowlisted since ActionEngine still supports them for other callers.
AGENT_ACTION_TYPES: FrozenSet[str] = frozenset(
    {
        "get_device_status",
        "turn_device_on",
        "turn_device_off",
        "all_on",
        "all_off",
        "add_schedule",
        "remove_schedule",
        "replace_device_schedule",
        "clear_device_schedule",
        "get_schedules",
        "upsert_policy_schedule",
        "create_every_n_days_cycle",
        "remove_policy_schedule",
        "get_policy_schedules",
        "get_weather_context",
        "get_current_time",
        "get_policy_decision_history",
        "record_user_feedback",
    }
)

_DEVICE = {"type": "string", "description": "Configured device name such as bed1 or pump."}
_DURATION = {
    "type": "number",
    "description": "Run duration in minutes. Must not exceed AGENT_MAX_DURATION_MINUTES.",
}
_TIME = {"type": "string", "description": "24-hour time HH:MM."}


def get_agent_tools() -> List[Dict[str, Any]]:
    """Return strict function schemas for the watering agent."""
    return [
        _fn(
            "get_recent_context",
            "Get this channel's working slots, summary, pending confirmations, and feedback.",
            {},
            [],
        ),
        _fn(
            "get_policy_decision_history",
            "Explain recent automatic watering decisions.",
            {"device": _DEVICE},
            [],
        ),
        _fn(
            "record_user_feedback",
            "Record an observation such as too wet or too dry.",
            {"device": _DEVICE, "feedback": {"type": "string"}},
            ["feedback"],
        ),
        _fn("get_device_status", "Show on/off status for one device or all devices.", {"device": _DEVICE}, []),
        _fn(
            "set_device_power",
            "Turn one or more devices on or off. For 'on', duration_minutes limits how long it "
            "stays on; for 'off', it delays the shutoff by that many minutes. For two or more "
            "specific devices (e.g. bed1 and bed2), pass them all in 'devices' in one call. Only "
            "use device 'all' when the user means literally every device, not as a shortcut for a "
            "named subset.",
            {
                "state": {"type": "string", "enum": ["on", "off"]},
                "device": _DEVICE,
                "devices": {
                    "type": "array",
                    "items": _DEVICE,
                    "description": "Multiple specific devices to act on together.",
                },
                "duration_minutes": _DURATION,
                "timeout": {"type": "integer"},
            },
            ["state"],
        ),
        _fn(
            "edit_schedule",
            "Add or remove a daily on/off time for a device.",
            {
                "op": {"type": "string", "enum": ["add", "remove"]},
                "device": _DEVICE,
                "action": {"type": "string", "enum": ["on", "off"]},
                "time": _TIME,
            },
            ["op", "device", "action", "time"],
        ),
        _fn(
            "clear_device_schedule",
            "Remove all schedules for a device. Requires confirmation. To replace a device's "
            "schedule wholesale, call this then edit_schedule with op='add' for each new time.",
            {"device": _DEVICE},
            ["device"],
        ),
        _fn("get_schedules", "List configured on/off schedules.", {"device": _DEVICE}, []),
        _fn(
            "upsert_policy_schedule",
            "Create or replace a flexible watering policy. Requires confirmation.",
            {"policy": {"type": "object"}},
            ["policy"],
        ),
        _fn(
            "create_every_n_days_cycle",
            "Create an every-N-days watering cycle. Requires confirmation.",
            {
                "device": _DEVICE,
                "every": {"type": "integer", "minimum": 1},
                "at": _TIME,
                "duration_minutes": _DURATION,
                "anchor_date": {"type": "string"},
            },
            ["device", "every", "at", "duration_minutes"],
        ),
        _fn(
            "remove_policy_schedule",
            "Delete a flexible policy by id. Requires confirmation.",
            {"policy_id": {"type": "string"}},
            ["policy_id"],
        ),
        _fn("get_policy_schedules", "List flexible watering cycles.", {}, []),
        _fn("get_weather_context", "Get the current weather context used by policies.", {}, []),
        _fn("get_current_time", "Get the bot host's local time.", {}, []),
        _fn(
            "respond_to_pending_action",
            "Confirm or cancel a pending action the user just replied to (e.g. said yes/sure/go "
            "ahead to confirm, or no/cancel/nevermind to cancel). Omit token when only one action "
            "is pending.",
            {"decision": {"type": "string", "enum": ["confirm", "cancel"]}, "token": {"type": "string"}},
            ["decision"],
        ),
    ]


def _fn(
    name: str,
    description: str,
    properties: Dict[str, Any],
    required: List[str],
) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }
