"""OpenAI integration for WaterBot with tool support."""

import json
import logging
from typing import Any, Dict, List

from openai import OpenAI

from . import policy as policy_model
from . import scheduler
from .config import OPENAI_API_KEY, OPENAI_MODEL
from .gpio import handler as gpio_handler
from .weather import WeatherContextProvider

logger = logging.getLogger("waterbot.openai")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def get_available_tools() -> List[Dict[str, Any]]:
    """Define the tools available to the OpenAI model."""
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


def execute_tool_call(function_name: str, arguments: Dict[str, Any]) -> str:
    """Execute a tool function call and return the result."""
    try:
        if function_name == "replace_device_schedule":
            device = arguments["device"]
            schedule_periods = arguments["schedule_periods"]

            from .config import get_schedules

            existing_schedules = get_schedules(device)
            removed_count = sum(len(times) for times in existing_schedules.values())
            replacement_schedules: Dict[str, List[str]] = {"on": [], "off": []}

            for period in schedule_periods:
                replacement_schedules["on"].append(period["start_time"])
                replacement_schedules["off"].append(period["end_time"])

            success = scheduler.replace_device_schedules(device, replacement_schedules)
            if not success:
                return f"Failed to replace schedule for '{device}'"

            result = f"Schedule replacement for '{device}' completed:\n"
            result += f"- Removed {removed_count} existing schedules\n"
            result += f"- Added {len(replacement_schedules['on']) + len(replacement_schedules['off'])} new schedules\n"

            # Show the new schedule
            result += f"\nNew schedule for {device}:\n"
            for i, period in enumerate(schedule_periods, 1):
                result += f"  Period {i}: {period['start_time']} to {period['end_time']}\n"

            return result

        elif function_name == "clear_device_schedule":
            device = arguments["device"]

            # Get existing schedules
            from .config import get_schedules

            existing_schedules = get_schedules(device)
            removed_count = 0

            # Remove all existing schedules
            for action in ["on", "off"]:
                if action in existing_schedules:
                    for time_str in existing_schedules[action][:]:  # Copy list to avoid modification during iteration
                        success = scheduler.remove_schedule(device, action, time_str)
                        if success:
                            removed_count += 1

            return f"Cleared all schedules for '{device}' - " f"removed {removed_count} schedule entries"

        elif function_name == "upsert_policy_schedule":
            saved_policy = scheduler.upsert_policy_schedule(arguments["policy"])
            return f"Saved flexible schedule:\n{policy_model.policy_summary(saved_policy)}"

        elif function_name == "create_every_n_days_cycle":
            policy_data = policy_model.create_every_n_days_policy(
                device=arguments["device"],
                every=int(arguments["every"]),
                at=arguments["at"],
                duration_minutes=float(arguments["duration_minutes"]),
                anchor_date=arguments.get("anchor_date"),
            )
            saved_policy = scheduler.upsert_policy_schedule(policy_data)
            return f"Saved flexible cycle:\n{policy_model.policy_summary(saved_policy)}"

        elif function_name == "remove_policy_schedule":
            policy_id = arguments["policy_id"]
            success = scheduler.remove_policy_schedule(policy_id)
            if success:
                return f"Removed flexible schedule: {policy_id}"
            return f"No such flexible schedule found: {policy_id}"

        elif function_name == "get_policy_schedules":
            policies = scheduler.get_policy_schedules()
            if not policies:
                return "No flexible policy schedules configured"
            result = "Flexible Policy Schedules:\n"
            for saved_policy in policies:
                result += f"- {policy_model.policy_summary(saved_policy)}\n"
            return result

        elif function_name == "get_weather_context":
            context = WeatherContextProvider().get_context()
            if not context:
                return "No weather context available"
            result = "Weather Context:\n"
            for key, value in sorted(context.items()):
                result += f"- {key}: {value}\n"
            return result

        elif function_name == "get_device_status":
            device = arguments.get("device")
            status = gpio_handler.get_status()
            if not status:
                return "No devices configured"

            if device:
                if device.lower() in status:
                    is_on = status[device.lower()]
                    return f"Device '{device}' is {'ON' if is_on else 'OFF'}"
                else:
                    return f"Device '{device}' not found"

            # Return all device statuses
            result = "Device Status:\n"
            for dev, is_on in status.items():
                result += f"- {dev}: {'ON' if is_on else 'OFF'}\n"
            return result

        elif function_name == "turn_device_on":
            device = arguments["device"]
            duration = arguments.get("duration_minutes")
            timeout = duration * 60 if duration else None

            if device.lower() == "all":
                gpio_handler.turn_all_on()
                return "All devices turned ON"
            else:
                success = gpio_handler.turn_on(device, timeout)
                if success:
                    time_msg = f" for {duration} minutes" if duration else ""
                    return f"Device '{device}' turned ON{time_msg}"
                else:
                    return f"Error: Unknown device '{device}'"

        elif function_name == "turn_device_off":
            device = arguments["device"]

            if device.lower() == "all":
                gpio_handler.turn_all_off()
                return "All devices turned OFF"
            else:
                success = gpio_handler.turn_off(device, None)
                if success:
                    return f"Device '{device}' turned OFF"
                else:
                    return f"Error: Unknown device '{device}'"

        elif function_name == "add_schedule":
            device = arguments["device"]
            action = arguments["action"]
            time_str = arguments["time"]

            success = scheduler.add_schedule(device, action, time_str)
            if success:
                return f"Added schedule: {device} {action} at {time_str}"
            else:
                return f"Failed to add schedule for {device}"

        elif function_name == "remove_schedule":
            device = arguments["device"]
            action = arguments["action"]
            time_str = arguments["time"]

            success = scheduler.remove_schedule(device, action, time_str)
            if success:
                return f"Removed schedule: {device} {action} at {time_str}"
            else:
                return f"No such schedule found: {device} {action} at {time_str}"

        elif function_name == "get_schedules":
            device = arguments.get("device")
            from .config import get_schedules

            schedules = get_schedules(device)
            if not schedules:
                if device:
                    return f"No schedules configured for device '{device}'"
                else:
                    return "No schedules configured"

            result = "Device Schedules:\n"

            # Handle the case where a specific device is requested
            if device:
                # schedules contains the actions for this specific device
                # e.g., {"on": ["06:20", "21:30"], "off": ["06:25", "21:35"]}
                result += f"{device.upper()}:\n"
                for action, times in schedules.items():
                    for time_str in times:
                        result += f"  {action.upper()} at {time_str}\n"
            else:
                # schedules contains all devices
                # e.g., {"bed1": {"on": [...], "off": [...]}, "bed2": {...}}
                for dev, actions in schedules.items():
                    result += f"{dev.upper()}:\n"
                    for action, times in actions.items():
                        for time_str in times:
                            result += f"  {action.upper()} at {time_str}\n"

            # Add next runs information
            next_runs = scheduler.get_next_runs()
            if next_runs:
                result += "\nNext scheduled runs:\n"
                for run in next_runs[:5]:  # Show next 5 runs
                    result += f"  {run['device']} {run['action']} at {run['time']} " f"(next: {run['next_run']})\n"

            return result

        elif function_name == "get_current_time":
            import subprocess  # nosec B404
            import time
            from datetime import datetime

            current_time = datetime.now()
            result = f"Current Time: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"

            # Also show timezone info if available
            try:
                tz_result = subprocess.run(  # nosec B603, B607
                    ["timedatectl", "show", "--property=Timezone", "--value"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if tz_result.returncode == 0 and tz_result.stdout.strip():
                    timezone = tz_result.stdout.strip()
                    result += f"\nTimezone: {timezone}"
            except (
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
                FileNotFoundError,
            ):
                try:
                    result += f"\nTimezone: {time.tzname[time.daylight]}"
                except Exception:  # nosec B110
                    pass

            return result

        elif function_name == "get_ip_addresses":
            import subprocess  # nosec B404

            ip_info = {}
            try:
                # Get all network interfaces except loopback
                net_result = subprocess.run(  # nosec
                    ["ls", "/sys/class/net/"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                interfaces = [iface for iface in net_result.stdout.strip().split() if iface != "lo"]

                for interface in interfaces:
                    try:
                        # Get IP address for this interface
                        ip_result = subprocess.run(  # nosec
                            ["ip", "addr", "show", interface],
                            capture_output=True,
                            text=True,
                            check=True,
                        )

                        # Parse IP address from output
                        for line in ip_result.stdout.split("\n"):
                            if "inet " in line and "127.0.0.1" not in line:
                                ip = line.strip().split()[1].split("/")[0]
                                if ip:
                                    ip_info[interface] = ip
                                    break

                    except subprocess.CalledProcessError:
                        continue

            except subprocess.CalledProcessError:
                logger.warning("Failed to get network interface information")

            if ip_info:
                result = "SSH Access Information:\n\n"
                for interface, ip in ip_info.items():
                    result += f"• ssh pi@{ip} (via {interface})\n"
            else:
                result = "⚠️ No network interfaces found with IP addresses.\n" "Please check your network connection."

            return result

        elif function_name == "test_notification":
            # Test a notification
            scheduler_instance = scheduler.get_scheduler()
            scheduler_instance._send_discord_notification("test_device", "on", True)
            return "Test notification sent via scheduler system"

        else:
            return f"Unknown function: {function_name}"

    except Exception as e:
        logger.error(f"Error executing tool call {function_name}: {e}", exc_info=True)
        return f"Error executing {function_name}: {str(e)}"


async def process_with_openai(message: str) -> str:
    """Process a message using OpenAI with tool support."""
    if not client:
        return "OpenAI is not configured. Please set OPENAI_API_KEY in your .env file."

    try:
        # System message to set context
        system_message = (
            "You are WaterBot, an intelligent agentic assistant that controls water "
            "devices. You operate GPIO pins on a Raspberry Pi and can plan and "
            "execute complex multi-step operations.\n\n"
            "CORE CAPABILITIES:\n"
            "- Device Control: turn on/off individual devices or all devices\n"
            "- Intelligent Scheduling: create, modify, and manage complex schedules\n"
            "- Flexible Policy Scheduling: every-N-days cycles, weekly cycles, "
            "seasonal windows, and weather-aware skip/shorten/lengthen rules\n"
            "- Status Monitoring: check current device states and schedules\n"
            "- System Info: get current time, weather context, IP addresses for "
            "SSH access\n"
            "- Planning & Execution: break down complex requests into multiple "
            "steps\n\n"
            "CRITICAL EXECUTION RULES:\n"
            "- ALWAYS USE TOOLS to execute requested actions - never just plan "
            "without executing\n"
            "- When users request schedule changes, you MUST call the appropriate "
            "tool functions\n"
            "- For schedule modifications, use replace_device_schedule tool to make "
            "changes\n"
            "- For every-N-days cycles or weather-aware behavior, use "
            "upsert_policy_schedule or create_every_n_days_cycle\n"
            "- Don't just describe what you'll do - actually do it by calling the "
            "tools\n"
            "- After planning an action, immediately execute it using the available "
            "tools\n\n"
            "AGENTIC BEHAVIOR:\n"
            "- Always plan multi-step operations before executing\n"
            "- When users request schedule changes, understand they want to REPLACE "
            "existing schedules unless specified otherwise\n"
            "- For schedule periods (e.g., 'run from 6:01 to 6:06'), create ON "
            "schedule at start time and OFF schedule at end time\n"
            "- For requests like 'every 3 days', 'unless it rains', 'shorten based "
            "on temperature', or 'skip when rain is forecast', create a flexible "
            "policy schedule with recurrence, duration, and rules\n"
            "- Be proactive - if someone says 'change schedule to X', remove old "
            "schedules and add new ones atomically\n"
            "- Explain your planned actions AND THEN EXECUTE THEM using tools\n\n"
            "TOOL USAGE EXAMPLES:\n"
            "- 'change bed1 schedule to run 6:01-6:06 and 21:21-21:26' →\n"
            "  1. Call get_schedules('bed1') to see current schedule\n"
            "  2. Call replace_device_schedule('bed1', [...]) with new periods\n"
            "- 'make bed1 run 2 minutes longer' →\n"
            "  1. Call get_schedules('bed1') to see current times\n"
            "  2. Calculate new end times (add 2 minutes)\n"
            "  3. Call replace_device_schedule('bed1', [...]) with updated times\n"
            "- 'add schedule for pump at 9:00' → Call add_schedule('pump', 'on', "
            "'09:00')\n"
            "- 'water bed1 every 3 days at 6am for 8 minutes unless it rained a "
            "quarter inch' → Call upsert_policy_schedule(...) with recurrence "
            "type every_n_days and a skip rule using rain_last_24h_inches\n"
            "- 'shorten by half if rain is forecast' → Add a policy rule with "
            "forecast_rain_next_12h_inches and duration_multiplier 0.5\n"
            "- 'schedules' → Call get_schedules() to show all schedules\n\n"
            "MANDATORY: When users request changes to schedules, you MUST call the "
            "modification tools. Just describing the plan without executing it via "
            "tools is not acceptable behavior."
        )

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": message},
        ]

        # Make initial call to OpenAI
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=get_available_tools(),
            tool_choice="auto",
            max_tokens=1000,
            temperature=0.7,
        )

        response_message = response.choices[0].message
        messages.append(response_message)

        # Handle multiple rounds of tool calls
        max_rounds = 5  # Prevent infinite loops
        current_round = 0

        while response_message.tool_calls and current_round < max_rounds:
            current_round += 1
            logger.info(f"Tool call round {current_round}")

            # Execute all tool calls in this round
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                logger.info(f"Executing tool: {function_name} with args: " f"{function_args}")

                # Execute the tool
                tool_result = execute_tool_call(function_name, function_args)

                # Add tool result to messages
                messages.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": tool_result,
                    }
                )

            # Get next response after tool execution
            next_response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                tools=get_available_tools(),
                tool_choice="auto",
                max_tokens=1000,
                temperature=0.7,
            )

            response_message = next_response.choices[0].message
            messages.append(response_message)

        return response_message.content or "I completed the requested action."

    except Exception as e:
        logger.error(f"Error processing OpenAI request: {e}", exc_info=True)
        return f"Sorry, I encountered an error processing your request: {str(e)}"
