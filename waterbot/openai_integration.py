"""OpenAI integration for WaterBot with tool support."""

import json
import logging
from typing import Any, Dict, List

from openai import OpenAI

from .actions import ActionEngine
from .agent.runtime import AgentRuntime, get_agent_tools
from .config import OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger("waterbot.openai")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def get_available_tools() -> List[Dict[str, Any]]:
    """Define the tools available to the OpenAI model."""
    return get_agent_tools()


def get_legacy_available_tools() -> List[Dict[str, Any]]:
    """Define the legacy tools available to the OpenAI model."""
    return [
        {
            "type": "function",
            "function": {
                "name": "replace_device_schedule",
                "description": (
                    "Replace all schedules for a device with new schedule periods. "
                    "This removes all existing schedules for the device and adds new "
                    "ones."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device": {
                            "type": "string",
                            "description": "Device name to replace schedules for",
                        },
                        "schedule_periods": {
                            "type": "array",
                            "description": ("List of schedule periods with start and end times"),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "start_time": {
                                        "type": "string",
                                        "description": ("Start time in HH:MM format (when device " "turns ON)"),
                                        "pattern": "^\\d{2}:\\d{2}$",
                                    },
                                    "end_time": {
                                        "type": "string",
                                        "description": ("End time in HH:MM format (when device " "turns OFF)"),
                                        "pattern": "^\\d{2}:\\d{2}$",
                                    },
                                },
                                "required": ["start_time", "end_time"],
                            },
                        },
                    },
                    "required": ["device", "schedule_periods"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "clear_device_schedule",
                "description": "Remove all schedules for a specific device",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device": {
                            "type": "string",
                            "description": "Device name to clear schedules for",
                        }
                    },
                    "required": ["device"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "upsert_policy_schedule",
                "description": (
                    "Create or replace a flexible watering policy. Use this for "
                    "every-N-days cycles, weather-aware schedules, seasonal windows, "
                    "or rules that skip, shorten, or lengthen runs."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "policy": {
                            "type": "object",
                            "description": (
                                "Policy object with id, device, recurrence, duration, "
                                "and optional rules. Recurrence types: daily, weekly, "
                                "every_n_days. Rule metrics include temperature_f, "
                                "rain_last_24h_inches, forecast_rain_next_12h_inches, "
                                "and rain_probability_next_12h."
                            ),
                        }
                    },
                    "required": ["policy"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_every_n_days_cycle",
                "description": "Create a simple flexible cycle that runs a device every N days",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device": {"type": "string", "description": "Device name"},
                        "every": {
                            "type": "integer",
                            "description": "Run every N days",
                            "minimum": 1,
                        },
                        "at": {
                            "type": "string",
                            "description": "Start time in HH:MM format",
                            "pattern": "^\\d{2}:\\d{2}$",
                        },
                        "duration_minutes": {
                            "type": "number",
                            "description": "Base watering duration in minutes",
                        },
                        "anchor_date": {
                            "type": "string",
                            "description": "Optional YYYY-MM-DD date that defines cycle day zero",
                        },
                    },
                    "required": ["device", "every", "at", "duration_minutes"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "remove_policy_schedule",
                "description": "Remove a flexible policy schedule by ID",
                "parameters": {
                    "type": "object",
                    "properties": {"policy_id": {"type": "string", "description": "Policy ID"}},
                    "required": ["policy_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_policy_schedules",
                "description": "List flexible policy schedules",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_weather_context",
                "description": "Get weather metrics available to flexible policy rules",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_device_status",
                "description": ("Get the current status of all devices or a specific device"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device": {
                            "type": "string",
                            "description": (
                                "Optional device name to get status for. "
                                "If not provided, returns status for all devices"
                            ),
                        }
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "turn_device_on",
                "description": ("Turn on a device, optionally for a specific duration"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device": {
                            "type": "string",
                            "description": ("Device name to turn on, or 'all' for all devices"),
                        },
                        "duration_minutes": {
                            "type": "integer",
                            "description": ("Optional duration in minutes to keep the device on"),
                        },
                    },
                    "required": ["device"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "turn_device_off",
                "description": ("Turn off a device"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device": {
                            "type": "string",
                            "description": ("Device name to turn off, or 'all' for all devices"),
                        }
                    },
                    "required": ["device"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "add_schedule",
                "description": ("Add a schedule for a device to turn on or off at a specific time"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device": {
                            "type": "string",
                            "description": "Device name to schedule",
                        },
                        "action": {
                            "type": "string",
                            "description": "Action to perform ('on' or 'off')",
                            "enum": ["on", "off"],
                        },
                        "time": {
                            "type": "string",
                            "description": "Time in HH:MM format (24-hour)",
                            "pattern": "^\\d{2}:\\d{2}$",
                        },
                    },
                    "required": ["device", "action", "time"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "remove_schedule",
                "description": "Remove a schedule for a device",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device": {
                            "type": "string",
                            "description": "Device name",
                        },
                        "action": {
                            "type": "string",
                            "description": "Action ('on' or 'off')",
                            "enum": ["on", "off"],
                        },
                        "time": {
                            "type": "string",
                            "description": "Time in HH:MM format (24-hour)",
                            "pattern": "^\\d{2}:\\d{2}$",
                        },
                    },
                    "required": ["device", "action", "time"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_schedules",
                "description": "Get all schedules or schedules for a specific device",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device": {
                            "type": "string",
                            "description": "Optional device name to get schedules for",
                        }
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": "Get the current time on the bot node",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_ip_addresses",
                "description": "Get IP addresses for SSH access to the bot node",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "test_notification",
                "description": "Send a test notification",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
    ]


def execute_tool_call(
    function_name: str,
    arguments: Dict[str, Any],
    channel_id: str = "default",
    source: str = "tool_direct",
    require_confirmation: bool = False,
) -> str:
    """Execute a tool function call and return the result."""
    try:
        if function_name == "get_recent_context":
            from .agent.memory import AgentMemory

            return json.dumps(AgentMemory().get_context(channel_id), indent=2)

        action_engine = ActionEngine()

        if function_name == "preview_action":
            preview = action_engine.preview_action(arguments["action_type"], arguments.get("arguments", {}))
            return preview.message

        if function_name == "execute_action":
            action_type = arguments["action_type"]
            action_arguments = arguments.get("arguments", {})
        else:
            action_type = function_name
            action_arguments = dict(arguments)
            if function_name == "record_user_feedback":
                action_arguments["channel_id"] = channel_id

        action_result = action_engine.execute_action(
            action_type,
            action_arguments,
            source=source,
            channel_id=channel_id,
            require_confirmation=require_confirmation,
        )
        if action_result.message == f"Unknown action: {function_name}":
            return f"Unknown function: {function_name}"
        return action_result.message

    except Exception as e:
        logger.error(f"Error executing tool call {function_name}: {e}", exc_info=True)
        return f"Error executing {function_name}: {str(e)}"


async def process_with_openai(
    message: str,
    channel_id: str = "default",
    author_id: str | None = None,
    author_name: str | None = None,
) -> str:
    """Process a message using OpenAI with tool support."""
    if not client:
        return "OpenAI is not configured. Please set OPENAI_API_KEY in your .env file."

    try:
        runtime = AgentRuntime(client=client, model=OPENAI_MODEL)
        return await runtime.process(message, channel_id, author_id, author_name)

    except Exception as e:
        logger.error(f"Error processing OpenAI request: {e}", exc_info=True)
        return f"Sorry, I encountered an error processing your request: {str(e)}"
