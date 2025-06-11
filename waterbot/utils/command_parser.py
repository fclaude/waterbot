import logging
import re

from ..config import DEVICE_TO_PIN

logger = logging.getLogger("command_parser")


def parse_command(text):
    """
    Parse a command string into an action and parameters

    Args:
        text (str): Command text from user

    Returns:
        tuple: (command_type, params) or (None, None) if invalid
    """
    text = text.strip().lower()

    # Status command
    if text == "status":
        return "status", {}

    # Scheduling commands
    if text == "schedules" or text == "schedule":
        return "show_schedules", {}

    # Schedule add: "schedule <device> <action> <time>"
    schedule_add_match = re.match(r"schedule\s+(\w+)\s+(on|off)\s+(\d{2}:\d{2})", text)
    if schedule_add_match:
        device, action, time_str = schedule_add_match.groups()
        if device not in DEVICE_TO_PIN:
            return "error", {"message": f"Unknown device: {device}"}

        # Validate time format (HH:MM where HH is 00-23 and MM is 00-59)
        hour, minute = time_str.split(":")
        if int(hour) > 23 or int(minute) > 59:
            return "help", {}  # Invalid time, fall through to help

        return "schedule_add", {"device": device, "action": action, "time": time_str}

    # Schedule remove: "unschedule <device> <action> <time>"
    schedule_remove_match = re.match(
        r"unschedule\s+(\w+)\s+(on|off)\s+(\d{2}:\d{2})", text
    )
    if schedule_remove_match:
        device, action, time_str = schedule_remove_match.groups()
        if device not in DEVICE_TO_PIN:
            return "error", {"message": f"Unknown device: {device}"}

        # Validate time format (HH:MM where HH is 00-23 and MM is 00-59)
        hour, minute = time_str.split(":")
        if int(hour) > 23 or int(minute) > 59:
            return "help", {}  # Invalid time, fall through to help

        return "schedule_remove", {"device": device, "action": action, "time": time_str}

    # All devices commands
    if text == "on all":
        return "all_on", {}

    if text == "off all":
        return "all_off", {}

    # Device-specific commands
    on_match = re.match(r"on\s+(\w+)(?:\s+(\d+))?", text)
    if on_match:
        device, time_str = on_match.groups()
        if device not in DEVICE_TO_PIN:
            logger.warning(f"Unknown device: {device}")
            return "error", {"message": f"Unknown device: {device}"}

        timeout = int(time_str) if time_str else None
        return "device_on", {"device": device, "timeout": timeout}

    off_match = re.match(r"off\s+(\w+)(?:\s+(\d+))?", text)
    if off_match:
        device, time_str = off_match.groups()
        if device not in DEVICE_TO_PIN:
            logger.warning(f"Unknown device: {device}")
            return "error", {"message": f"Unknown device: {device}"}

        timeout = int(time_str) if time_str else None
        return "device_off", {"device": device, "timeout": timeout}

    # Unknown command
    return "help", {}
