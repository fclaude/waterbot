import os
import re
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Signal configuration
SIGNAL_PHONE_NUMBER = os.getenv("SIGNAL_PHONE_NUMBER")
SIGNAL_GROUP_ID = os.getenv("SIGNAL_GROUP_ID")

# Operation mode
OPERATION_MODE = os.getenv("OPERATION_MODE", "emulation").lower()
IS_EMULATION = OPERATION_MODE != "rpi"

# Default timeout
DEFAULT_TIMEOUT = int(os.getenv("DEFAULT_TIMEOUT", "3600"))

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

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

# Validate configuration
def validate_config():
    """Validate that all required configuration variables are set."""
    if not SIGNAL_PHONE_NUMBER:
        raise ValueError("SIGNAL_PHONE_NUMBER is not set in .env file")
    if not SIGNAL_GROUP_ID:
        raise ValueError("SIGNAL_GROUP_ID is not set in .env file")
    if not DEVICE_TO_PIN:
        raise ValueError("No device to GPIO pin mappings found in .env file")
    
    return True
