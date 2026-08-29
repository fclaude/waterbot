"""Configuration management for WaterBot."""

import json
import os
import re
from copy import deepcopy
from tempfile import NamedTemporaryFile
from typing import Any, Callable, Dict, Optional

load_dotenv: Callable[[], bool]
try:
    from dotenv import load_dotenv as _load_dotenv

    load_dotenv = _load_dotenv
except ImportError:

    def _fallback_load_dotenv() -> bool:
        """Fallback when python-dotenv is not installed."""
        return False

    load_dotenv = _fallback_load_dotenv


# Load environment variables from .env file
load_dotenv()

# Discord configuration
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")

# OpenAI-compatible LLM configuration (optional; enables natural-language control).
# Point OPENAI_BASE_URL at any OpenAI Chat Completions-compatible server
# (OpenAI, OpenRouter, vLLM, Ollama, LiteLLM, etc.). Leave unset for api.openai.com.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL") or "").strip() or None


def is_openai_configured() -> bool:
    """Return True when the conversational LLM client can be created.

    An API key enables the default OpenAI endpoint. A custom OPENAI_BASE_URL also
    enables the client (local/self-hosted servers often accept a dummy key).
    """
    return bool(OPENAI_API_KEY) or bool(OPENAI_BASE_URL)


# Operation mode
OPERATION_MODE = os.getenv("OPERATION_MODE", "emulation").lower()
IS_EMULATION = OPERATION_MODE != "rpi"

# Default timeout (in minutes)
DEFAULT_TIMEOUT = int(os.getenv("DEFAULT_TIMEOUT", "60"))

# Relay default state. Per-device overrides use RELAY_DEFAULT_<DEVICE>=on|off.
RELAY_DEFAULT_STATE = os.getenv("RELAY_DEFAULT_STATE", "off").lower()
RELAY_CLEANUP_STATE = os.getenv("RELAY_CLEANUP_STATE", RELAY_DEFAULT_STATE).lower()
# Relay polarity. Per-device overrides use RELAY_ACTIVE_<DEVICE>=high|low.
RELAY_ACTIVE_STATE = os.getenv("RELAY_ACTIVE_STATE", "high").lower()

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# Scheduling configuration
ENABLE_SCHEDULING = os.getenv("ENABLE_SCHEDULING", "false").lower() == "true"
SCHEDULE_CONFIG_FILE = os.getenv("SCHEDULE_CONFIG_FILE", "data/schedules.json")
POLICY_SCHEDULE_CONFIG_FILE = os.getenv("POLICY_SCHEDULE_CONFIG_FILE", "data/schedule_policies.json")

# Optional weather context for policy schedules.
WEATHER_PROVIDER = os.getenv("WEATHER_PROVIDER", "none").lower()
WEATHER_LATITUDE = os.getenv("WEATHER_LATITUDE")
WEATHER_LONGITUDE = os.getenv("WEATHER_LONGITUDE")
WEATHER_CONTEXT_FILE = os.getenv("WEATHER_CONTEXT_FILE")
WEATHER_REQUEST_TIMEOUT = float(os.getenv("WEATHER_REQUEST_TIMEOUT", "10"))

# Conversational agent state.
AGENT_DB_FILE = os.getenv("AGENT_DB_FILE", "data/waterbot_agent.db")
AGENT_MEMORY_RETENTION_DAYS = int(os.getenv("AGENT_MEMORY_RETENTION_DAYS", "30"))
AGENT_CONFIRMATION_TIMEOUT_MINUTES = int(os.getenv("AGENT_CONFIRMATION_TIMEOUT_MINUTES", "10"))
AGENT_REQUIRE_CONFIRMATION = os.getenv("AGENT_REQUIRE_CONFIRMATION", "true").lower() == "true"
# Recent turns sent to the model as real chat messages.
AGENT_CONTEXT_MESSAGE_LIMIT = int(os.getenv("AGENT_CONTEXT_MESSAGE_LIMIT", "48"))
# Max characters kept in the long-term channel summary.
AGENT_SUMMARY_MAX_CHARS = int(os.getenv("AGENT_SUMMARY_MAX_CHARS", "4000"))
# Max agent tool-calling rounds per user message.
AGENT_MAX_TOOL_ROUNDS = int(os.getenv("AGENT_MAX_TOOL_ROUNDS", "6"))
# Hard cap on watering/device run duration requested via chat or tools.
AGENT_MAX_DURATION_MINUTES = int(os.getenv("AGENT_MAX_DURATION_MINUTES", "120"))
# Discord-friendly cap on the model's final reply.
AGENT_MAX_REPLY_CHARS = int(os.getenv("AGENT_MAX_REPLY_CHARS", "800"))
# Approximate character budget for the assembled chat prompt (system + history).
AGENT_PROMPT_CHAR_BUDGET = int(os.getenv("AGENT_PROMPT_CHAR_BUDGET", "24000"))
# How many audited actions to inject into the system prompt.
AGENT_RECENT_ACTIONS_LIMIT = int(os.getenv("AGENT_RECENT_ACTIONS_LIMIT", "15"))
# LLM calls allowed per author (or channel) per rolling minute.
AGENT_RATE_LIMIT_PER_MINUTE = int(os.getenv("AGENT_RATE_LIMIT_PER_MINUTE", "8"))
# Optional extra LLM pass to rewrite the folded channel summary.
AGENT_LLM_SUMMARIZE = os.getenv("AGENT_LLM_SUMMARIZE", "false").lower() == "true"

# Optional local web interface.
# Default to localhost; set WEB_HOST=0.0.0.0 only for trusted LAN deployments.
ENABLE_WEB_INTERFACE = os.getenv("ENABLE_WEB_INTERFACE", "false").lower() == "true"
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))
WEB_AUTH_USERNAME = os.getenv("WEB_AUTH_USERNAME", "admin")
WEB_AUTH_PASSWORD = os.getenv("WEB_AUTH_PASSWORD")
WEB_AUTH_TOKEN = os.getenv("WEB_AUTH_TOKEN")
WEB_PUBLIC_SCHEDULES = os.getenv("WEB_PUBLIC_SCHEDULES", "false").lower() == "true"

# Load device to GPIO pin mapping
DEVICE_TO_PIN = {}
DEVICE_DEFAULT_STATES = {}
DEVICE_ACTIVE_STATES = {}

for key, value in os.environ.items():
    if key.startswith("DEVICE_"):
        device_name = key[7:].lower()  # Remove "DEVICE_" prefix and lowercase
        try:
            pin = int(value)
            DEVICE_TO_PIN[device_name] = pin
        except ValueError:
            print(f"Warning: Invalid GPIO pin value for {key}: {value}")

for key, value in os.environ.items():
    if key.startswith("RELAY_DEFAULT_") and key not in {
        "RELAY_DEFAULT_STATE",
    }:
        device_name = key[len("RELAY_DEFAULT_") :].lower()
        DEVICE_DEFAULT_STATES[device_name] = value.lower()

for key, value in os.environ.items():
    if key.startswith("RELAY_ACTIVE_") and key not in {
        "RELAY_ACTIVE_STATE",
    }:
        device_name = key[len("RELAY_ACTIVE_") :].lower()
        DEVICE_ACTIVE_STATES[device_name] = value.lower()


def parse_relay_state(value: str) -> bool:
    """Parse a logical relay state string into a boolean."""
    normalized = value.strip().lower()
    if normalized in {"on", "true", "1", "yes", "high"}:
        return True
    if normalized in {"off", "false", "0", "no", "low"}:
        return False
    raise ValueError(f"Invalid relay state '{value}'. Use on or off.")


def parse_gpio_level(value: str) -> bool:
    """Parse a GPIO output level string into a boolean."""
    normalized = value.strip().lower()
    if normalized in {"high", "true", "1", "yes", "on"}:
        return True
    if normalized in {"low", "false", "0", "no", "off"}:
        return False
    raise ValueError(f"Invalid relay active state '{value}'. Use high or low.")


def get_device_default_state(device: str) -> bool:
    """Get the configured logical startup state for a device."""
    state = DEVICE_DEFAULT_STATES.get(device.lower(), RELAY_DEFAULT_STATE)
    return parse_relay_state(state)


def get_device_cleanup_state(device: str) -> bool:
    """Get the configured logical cleanup state for a device."""
    if RELAY_CLEANUP_STATE == "default":
        return get_device_default_state(device)
    return parse_relay_state(RELAY_CLEANUP_STATE)


def get_device_active_state(device: str) -> bool:
    """Get the GPIO output level that means logical ON for a device."""
    state = DEVICE_ACTIVE_STATES.get(device.lower(), RELAY_ACTIVE_STATE)
    return parse_gpio_level(state)


def get_device_gpio_state(device: str, logical_state: bool) -> bool:
    """Convert a logical relay state into the GPIO output level for a device."""
    active_state = get_device_active_state(device)
    return active_state if logical_state else not active_state


# Load scheduling configuration
DEVICE_SCHEDULES: Dict[str, Any] = {}


def load_schedules() -> None:
    """Load device schedules from JSON configuration file."""
    global DEVICE_SCHEDULES

    if os.path.exists(SCHEDULE_CONFIG_FILE):
        try:
            with open(SCHEDULE_CONFIG_FILE, "r") as f:
                DEVICE_SCHEDULES = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load schedule config file " f"{SCHEDULE_CONFIG_FILE}: {e}")
            DEVICE_SCHEDULES = {}
    else:
        DEVICE_SCHEDULES = load_schedules_from_env()


def load_schedules_from_env() -> Dict[str, Any]:
    """Load legacy on/off schedules from SCHEDULE_<DEVICE>_<ACTION> env vars."""
    schedules: Dict[str, Any] = {}

    for key, value in os.environ.items():
        if not key.startswith("SCHEDULE_"):
            continue

        parts = key.split("_")
        if len(parts) < 3:
            continue

        device = "_".join(parts[1:-1]).lower()
        action = parts[-1].lower()
        if device not in DEVICE_TO_PIN or action not in {"on", "off"}:
            continue

        times = []
        for time_str in value.split(","):
            normalized_time = time_str.strip()
            if _valid_schedule_time(normalized_time):
                times.append(normalized_time)
            else:
                print(f"Warning: Ignoring invalid schedule time {normalized_time} for {key}")

        if times:
            schedules.setdefault(device, {})[action] = sorted(set(times))

    return schedules


def save_schedules() -> bool:
    """Save current device schedules to configuration file."""
    try:
        directory = os.path.dirname(os.path.abspath(SCHEDULE_CONFIG_FILE)) or "."
        os.makedirs(directory, exist_ok=True)
        with NamedTemporaryFile("w", delete=False, dir=directory) as f:
            json.dump(DEVICE_SCHEDULES, f, indent=2)
            f.write("\n")
            temp_path = f.name
        os.replace(temp_path, SCHEDULE_CONFIG_FILE)
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

    if not _valid_schedule_time(time):
        return False

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
    if device in DEVICE_SCHEDULES and action in DEVICE_SCHEDULES[device] and time in DEVICE_SCHEDULES[device][action]:
        DEVICE_SCHEDULES[device][action].remove(time)

        # Clean up empty entries
        if not DEVICE_SCHEDULES[device][action]:
            del DEVICE_SCHEDULES[device][action]

        if not DEVICE_SCHEDULES[device]:
            del DEVICE_SCHEDULES[device]

        return save_schedules()

    return False


def replace_device_schedules(device: str, schedules: Dict[str, Any]) -> bool:
    """Replace all schedules for a device atomically."""
    if device not in DEVICE_TO_PIN:
        return False

    normalized: Dict[str, Any] = {}
    for action, times in schedules.items():
        if action not in {"on", "off"} or not isinstance(times, list):
            return False

        valid_times = []
        for time_str in times:
            if not isinstance(time_str, str) or not _valid_schedule_time(time_str):
                return False
            valid_times.append(time_str)

        if valid_times:
            normalized[action] = sorted(set(valid_times))

    previous_schedules = deepcopy(DEVICE_SCHEDULES)
    saved = False
    try:
        if normalized:
            DEVICE_SCHEDULES[device] = normalized
        elif device in DEVICE_SCHEDULES:
            del DEVICE_SCHEDULES[device]

        saved = save_schedules()
        return saved
    finally:
        if not saved:
            DEVICE_SCHEDULES.clear()
            DEVICE_SCHEDULES.update(previous_schedules)


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


def _valid_schedule_time(time: str) -> bool:
    """Validate HH:MM time strings."""
    if not re.match(r"^\d{2}:\d{2}$", time):
        return False
    hour, minute = time.split(":")
    return int(hour) <= 23 and int(minute) <= 59


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
    else:
        print("Running in offline mode - Discord validation skipped")

    if not DEVICE_TO_PIN:
        raise ValueError("No device to GPIO pin mappings found in .env file")

    # Validate relay default configuration.
    for device in DEVICE_TO_PIN:
        get_device_default_state(device)
        get_device_cleanup_state(device)
        get_device_active_state(device)

    # Validate flexible policy schedules if present.
    try:
        from .policy import list_policies

        list_policies()
    except ValueError as e:
        raise ValueError(f"Invalid flexible schedule policy: {e}") from e

    if ENABLE_WEB_INTERFACE and not (WEB_AUTH_PASSWORD or WEB_AUTH_TOKEN):
        raise ValueError("ENABLE_WEB_INTERFACE requires WEB_AUTH_PASSWORD or WEB_AUTH_TOKEN")

    return True
