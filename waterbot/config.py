"""Configuration management for WaterBot."""

import json
import os
import re
from typing import Any, Dict, Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Discord configuration
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")

# Operation mode
OPERATION_MODE = os.getenv("OPERATION_MODE", "emulation").lower()
IS_EMULATION = OPERATION_MODE != "rpi"

# Default timeout
DEFAULT_TIMEOUT = int(os.getenv("DEFAULT_TIMEOUT", "3600"))

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# Scheduling configuration
ENABLE_SCHEDULING = os.getenv("ENABLE_SCHEDULING", "false").lower() == "true"
SCHEDULE_CONFIG_FILE = os.getenv("SCHEDULE_CONFIG_FILE", "schedules.json")

# Load device to GPIO pin mapping
DEVICE_TO_PIN = {}

for key, value in os.environ.items():
    if key.startswith("DEVICE_"):
        device_name = key[7:].lower()  # Remove "DEVICE_" prefix and lowercase
        try:
            pin = int(value)
            DEVICE_TO_PIN[device_name] = pin
        except ValueError:
            print(f"Warning: Invalid GPIO pin value for {key}: {value}")

# Load scheduling configuration
DEVICE_SCHEDULES = {}


def load_schedules() -> None:
    """Load device schedules from configuration file or env variables."""
    global DEVICE_SCHEDULES

    # First try to load from JSON file
    if os.path.exists(SCHEDULE_CONFIG_FILE):
        try:
            with open(SCHEDULE_CONFIG_FILE, "r") as f:
                DEVICE_SCHEDULES = json.load(f)
            return
        except (json.JSONDecodeError, IOError) as e:
            print(
                f"Warning: Could not load schedule config file "
                f"{SCHEDULE_CONFIG_FILE}: {e}"
            )

    # Fallback to environment variables
    # Format: SCHEDULE_<DEVICE>_<ACTION>=HH:MM[,HH:MM,...]
    # Example: SCHEDULE_PUMP_ON=08:00,20:00
    #          SCHEDULE_PUMP_OFF=12:00,23:00
    for key, value in os.environ.items():
        if key.startswith("SCHEDULE_"):
            parts = key.split("_")
            if len(parts) >= 3:
                device = "_".join(parts[1:-1]).lower()
                action = parts[-1].lower()

                if device in DEVICE_TO_PIN and action in ["on", "off"]:
                    # Parse time values (comma-separated)
                    times = []
                    for time_str in value.split(","):
                        time_str = time_str.strip()
                        if re.match(r"^\d{2}:\d{2}$", time_str):
                            # Validate time format (HH:MM where HH is 00-23
                            # and MM is 00-59)
                            hour, minute = time_str.split(":")
                            if int(hour) <= 23 and int(minute) <= 59:
                                times.append(time_str)
                            else:
                                print(
                                    f"Warning: Invalid time format in "
                                    f"{key}: {time_str}"
                                )
                        else:
                            print(  # type: ignore[unreachable]
                                f"Warning: Invalid time format in {key}: " f"{time_str}"
                            )

                    if times:
                        if device not in DEVICE_SCHEDULES:
                            DEVICE_SCHEDULES[device] = {}
                        DEVICE_SCHEDULES[device][action] = times


def save_schedules() -> bool:
    """Save current device schedules to configuration file."""
    try:
        with open(SCHEDULE_CONFIG_FILE, "w") as f:
            json.dump(DEVICE_SCHEDULES, f, indent=2)
        return True
    except IOError as e:
        print(f"Error saving schedules: {e}")
        return False


def add_schedule(device: str, action: str, time: str) -> bool:
    """Add a schedule for a device.

    Args:
        device (str): Device name
        action (str): 'on' or 'off'
        time (str): Time in HH:MM format

    Returns:
        bool: Success status
    """
    if device not in DEVICE_TO_PIN:
        return False

    if action not in ["on", "off"]:
        return False

    if not re.match(r"^\d{2}:\d{2}$", time):
        return False  # type: ignore[unreachable]

    if device not in DEVICE_SCHEDULES:
        DEVICE_SCHEDULES[device] = {}

    if action not in DEVICE_SCHEDULES[device]:
        DEVICE_SCHEDULES[device][action] = []

    if time not in DEVICE_SCHEDULES[device][action]:
        DEVICE_SCHEDULES[device][action].append(time)
        DEVICE_SCHEDULES[device][action].sort()
        return save_schedules()

    return True


def remove_schedule(device: str, action: str, time: str) -> bool:
    """Remove a schedule for a device.

    Args:
        device (str): Device name
        action (str): 'on' or 'off'
        time (str): Time in HH:MM format

    Returns:
        bool: Success status
    """
    if (
        device in DEVICE_SCHEDULES
        and action in DEVICE_SCHEDULES[device]
        and time in DEVICE_SCHEDULES[device][action]
    ):
        DEVICE_SCHEDULES[device][action].remove(time)

        # Clean up empty entries
        if not DEVICE_SCHEDULES[device][action]:
            del DEVICE_SCHEDULES[device][action]

        if not DEVICE_SCHEDULES[device]:
            del DEVICE_SCHEDULES[device]

        return save_schedules()

    return False


def get_schedules(device: Optional[str] = None) -> Dict[str, Any]:
    """Get schedules for a device or all devices.

    Args:
        device (str, optional): Device name. If None, returns all schedules.

    Returns:
        dict: Schedule configuration
    """
    if device:
        return dict(DEVICE_SCHEDULES.get(device, {}))
    return dict(DEVICE_SCHEDULES.copy())


# Load schedules on import
load_schedules()


# Validate configuration
def validate_config() -> bool:
    """Validate that all required configuration variables are set."""
    if not DISCORD_BOT_TOKEN:
        raise ValueError("DISCORD_BOT_TOKEN is not set in .env file")
    if not DISCORD_CHANNEL_ID:
        raise ValueError("DISCORD_CHANNEL_ID is not set in .env file")
    if not DEVICE_TO_PIN:
        raise ValueError("No device to GPIO pin mappings found in .env file")

    return True
