#!/usr/bin/env python3
"""Run script for WaterBot.

This script provides a simple way to run the waterbot.
"""

import argparse
import logging
import os
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("waterbot_runner")


def check_env_file() -> bool:
    """Check if .env file exists and create it if needed."""
    if not os.path.exists(".env"):
        logger.info("No .env file found. Creating a template .env file.")

        # Create a template .env file
        env_template = """# Discord Configuration
DISCORD_BOT_TOKEN="your_discord_bot_token_here"
DISCORD_CHANNEL_ID="123456789012345678"

# OpenAI-compatible LLM (optional, enables natural-language control)
OPENAI_API_KEY="your_openai_api_key_here"  # pragma: allowlist secret
OPENAI_MODEL="gpt-4o-mini"
# OPENAI_BASE_URL="http://127.0.0.1:11434/v1"

# Operation Mode (rpi or emulation)
OPERATION_MODE=emulation

# Device to GPIO Pin Mapping
# Format: DEVICE_NAME=GPIO_PIN_NUMBER
DEVICE_LIGHT=17
DEVICE_FAN=18
DEVICE_PUMP=27
DEVICE_HEATER=22

# Relay defaults
RELAY_DEFAULT_STATE=off
RELAY_CLEANUP_STATE=off

# Default timeout in minutes (optional, for timed operations)
DEFAULT_TIMEOUT=60

# Scheduling Configuration
ENABLE_SCHEDULING=true
SCHEDULE_CONFIG_FILE=schedules.json
POLICY_SCHEDULE_CONFIG_FILE=schedule_policies.json

# Conversational agent memory and confirmations
AGENT_DB_FILE=waterbot_agent.db
AGENT_MEMORY_RETENTION_DAYS=30
AGENT_CONFIRMATION_TIMEOUT_MINUTES=10
AGENT_REQUIRE_CONFIRMATION=true

# Optional authenticated web interface
ENABLE_WEB_INTERFACE=false
WEB_HOST=0.0.0.0
WEB_PORT=8080
WEB_AUTH_USERNAME=admin
# WEB_AUTH_PASSWORD="change_me"  # pragma: allowlist secret
# WEB_AUTH_TOKEN="optional_api_token"  # pragma: allowlist secret
WEB_PUBLIC_SCHEDULES=true

# Optional weather context for flexible policy schedules
WEATHER_PROVIDER=none

# Logging Configuration
# Set log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO
# Set to true to enable more verbose debugging output
DEBUG_MODE=false
"""
        with open(".env", "w") as f:
            f.write(env_template)

        logger.info("Template .env file created. Please edit it with your " "configuration before running again.")
        return False

    return True


def main() -> int:
    """Run the WaterBot application."""
    parser = argparse.ArgumentParser(description="Run WaterBot Discord GPIO Controller")
    parser.add_argument("--emulation", action="store_true", help="Force emulation mode for testing")
    parser.add_argument("--test", action="store_true", help="Run the test_emulation.py script")
    args = parser.parse_args()

    # Check if .env file exists
    if not check_env_file():
        return 1

    # Force emulation mode if requested
    if args.emulation:
        os.environ["OPERATION_MODE"] = "emulation"
        logger.info("Forcing emulation mode")

    if args.test:
        logger.info("Running emulation test")
        import test_emulation  # noqa: F401

        return 0

    # Import and run the main bot module
    logger.info("Starting WaterBot")
    try:
        from waterbot.bot import main as bot_main

        bot_main()
    except ImportError:
        logger.error("Failed to import waterbot. Make sure the package is installed.")
        return 1
    except Exception as e:
        logger.error(f"Error running waterbot: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
