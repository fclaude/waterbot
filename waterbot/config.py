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

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Operation mode
OPERATION_MODE = os.getenv("OPERATION_MODE", "emulation").lower()
IS_EMULATION = OPERATION_MODE != "rpi"

# Default timeout (in minutes)
DEFAULT_TIMEOUT = int(os.getenv("DEFAULT_TIMEOUT", "60"))

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
    """Load device schedules from JSON configuration file."""
    global DEVICE_SCHEDULES

    # Load from JSON file only
    if os.path.exists(SCHEDULE_CONFIG_FILE):
        try:
            with open(SCHEDULE_CONFIG_FILE, "r") as f:
                DEVICE_SCHEDULES = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(
                f"Warning: Could not load schedule config file "
                f"{SCHEDULE_CONFIG_FILE}: {e}"
            )
            DEVICE_SCHEDULES = {}
    else:
        # No config file exists, start with empty schedules
        DEVICE_SCHEDULES = {}


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
    import os

    # Check if we're running in offline/scheduling-only mode
    offline_mode = os.getenv("OFFLINE_MODE", "false").lower() == "true"

    if not offline_mode:
        if not DISCORD_BOT_TOKEN:
            raise ValueError("DISCORD_BOT_TOKEN is not set in .env file")
        if not DISCORD_CHANNEL_ID:
            raise ValueError("DISCORD_CHANNEL_ID is not set in .env file")
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in .env file")
    else:
        print("Running in offline mode - Discord validation skipped")

    if not DEVICE_TO_PIN:
        raise ValueError("No device to GPIO pin mappings found in .env file")

    return True
