"""Allowlisted OpenAI tool schemas for WaterBot."""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List

# Tools the model may call. IP lookup and test notifications stay as typed commands.
AGENT_TOOL_NAMES: FrozenSet[str] = frozenset(
    {
        "preview_action",
        "execute_action",
        "get_recent_context",
        "get_policy_decision_history",
        "record_user_feedback",
        "get_device_status",
        "turn_device_on",
        "turn_device_off",
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
        "confirm_pending_action",
        "cancel_pending_action",
    }
)

# execute_action / preview_action may only target these WaterBot actions.
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
            "preview_action",
            "Preview a watering action without executing it.",
            {
                "action_type": {"type": "string", "enum": sorted(AGENT_ACTION_TYPES)},
                "arguments": {"type": "object"},
            },
            ["action_type"],
        ),
        _fn(
            "execute_action",
            "Execute a watering action. Risky changes return a confirmation token.",
            {
                "action_type": {"type": "string", "enum": sorted(AGENT_ACTION_TYPES)},
                "arguments": {"type": "object"},
            },
            ["action_type"],
        ),
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
            "turn_device_on",
            "Turn one or more devices on, optionally for a limited number of minutes. For two or "
            "more specific devices (e.g. bed1 and bed2), pass them all in 'devices' in one call. "
            "Only use device 'all' when the user means literally every device, not as a shortcut "
            "for a named subset.",
            {
                "device": _DEVICE,
                "devices": {
                    "type": "array",
                    "items": _DEVICE,
                    "description": "Multiple specific devices to turn on together.",
                },
                "duration_minutes": _DURATION,
                "timeout": {"type": "integer"},
            },
            [],
        ),
        _fn(
            "turn_device_off",
            "Turn one or more devices off, optionally after a delay in minutes. For two or more "
            "specific devices, pass them all in 'devices' in one call. Only use device 'all' when "
            "the user means literally every device, not as a shortcut for a named subset.",
            {
                "device": _DEVICE,
                "devices": {
                    "type": "array",
                    "items": _DEVICE,
                    "description": "Multiple specific devices to turn off together.",
                },
                "duration_minutes": _DURATION,
                "timeout": {"type": "integer"},
            },
            [],
        ),
        _fn(
            "add_schedule",
            "Add a daily on/off time for a device.",
            {"device": _DEVICE, "action": {"type": "string", "enum": ["on", "off"]}, "time": _TIME},
            ["device", "action", "time"],
        ),
        _fn(
            "remove_schedule",
            "Remove a daily on/off time for a device.",
            {"device": _DEVICE, "action": {"type": "string", "enum": ["on", "off"]}, "time": _TIME},
            ["device", "action", "time"],
        ),
        _fn(
            "replace_device_schedule",
            "Replace every schedule period for a device. Requires confirmation.",
            {
                "device": _DEVICE,
                "schedule_periods": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"start_time": _TIME, "end_time": _TIME},
                        "required": ["start_time", "end_time"],
                        "additionalProperties": False,
                    },
                },
            },
            ["device", "schedule_periods"],
        ),
        _fn(
            "clear_device_schedule",
            "Remove all schedules for a device. Requires confirmation.",
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
            "confirm_pending_action",
            "Confirm and execute a pending action the user just agreed to (e.g. said yes, sure, "
            "go ahead). Omit token when only one action is pending.",
            {"token": {"type": "string"}},
            [],
        ),
        _fn(
            "cancel_pending_action",
            "Cancel a pending action the user just declined (e.g. said no, cancel, nevermind). "
            "Omit token when only one action is pending.",
            {"token": {"type": "string"}},
            [],
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
