"""Command parsing utilities for WaterBot."""

import logging
import re
from typing import Any, Dict, Optional, Tuple

from ..config import DEFAULT_TIMEOUT, DEVICE_TO_PIN

logger = logging.getLogger("command_parser")


def parse_command(text: str) -> Tuple[Optional[str], Dict[str, Any]]:
    """Parse a command string into an action and parameters.

    Args:
        text (str): Command text from user

    Returns:
        tuple: (command_type, params) or (None, None) if invalid
    """
    text = text.strip().lower()

    # Status command
    if text == "status":
        return "status", {}

    # Test, time, and ip commands
    if text == "test":
        return "test", {}

    if text == "time":
        return "time", {}

    if text == "ip":
        return "ip", {}

    # Device-specific schedule query: "schedule for <device>" or "schedules for <device>"
    schedule_for_match = re.match(r"(?:schedule|schedules)\s+for\s+(\w+)", text)
    if schedule_for_match:
        device = schedule_for_match.group(1)
        if device not in DEVICE_TO_PIN:
            return "error", {"message": f"Unknown device: {device}"}
        return "show_device_schedules", {"device": device}

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
    schedule_remove_match = re.match(r"unschedule\s+(\w+)\s+(on|off)\s+(\d{2}:\d{2})", text)
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
        return "all_on", {"timeout": DEFAULT_TIMEOUT * 60}

    if text == "off all":
        return "all_off", {"timeout": DEFAULT_TIMEOUT * 60}

    # Device-specific commands
    on_match = re.match(r"on\s+(\w+)(?:\s+(\d+))?", text)
    if on_match:
        device, time_str = on_match.groups()
        if device not in DEVICE_TO_PIN:
            logger.warning(f"Unknown device: {device}")
            return "error", {"message": f"Unknown device: {device}"}

        # Use DEFAULT_TIMEOUT if no timeout specified, convert minutes to seconds
        timeout = (int(time_str) * 60) if time_str else (DEFAULT_TIMEOUT * 60)
        return "device_on", {"device": device, "timeout": timeout}

    off_match = re.match(r"off\s+(\w+)(?:\s+(\d+))?", text)
    if off_match:
        device, time_str = off_match.groups()
        if device not in DEVICE_TO_PIN:
            logger.warning(f"Unknown device: {device}")
            return "error", {"message": f"Unknown device: {device}"}

        # Off command should be permanent - no timeout
        timeout = None
        return "device_off", {"device": device, "timeout": timeout}

    # Simple scheduling commands (must be after more specific schedule patterns)
    if text == "schedules" or text == "schedule":
        return "show_schedules", {}

    # Unknown command
    return "help", {}
