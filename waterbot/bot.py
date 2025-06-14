#!/usr/bin/env python3
"""Main bot entry point for WaterBot."""
import logging
import signal
import sys
from typing import Any

from . import scheduler
from .config import DEBUG_MODE, ENABLE_SCHEDULING, LOG_LEVEL, validate_config
from .discord.bot import WaterBot
from .gpio import handler as gpio_handler

# Configure logging
log_level = getattr(logging, LOG_LEVEL)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("waterbot.log")],
)

# Configure root logger
logger = logging.getLogger("waterbot")
if DEBUG_MODE:
    logger.setLevel(logging.DEBUG)
    # Also set DEBUG level for all discord bot loggers
    logging.getLogger("discord_bot").setLevel(logging.DEBUG)

logger.debug(
    "Logging initialized with level=%s, debug_mode=%s",
    LOG_LEVEL,
    DEBUG_MODE,
)


def handle_shutdown(signum: int, frame: Any) -> None:
    """Handle shutdown signals."""
    logger.info("Received shutdown signal")
    if hasattr(handle_shutdown, "bot") and handle_shutdown.bot is not None:
        handle_shutdown.bot.stop_bot()
    scheduler.stop_scheduler()
    sys.exit(0)


def main() -> None:
    """Start the WaterBot application."""
    logger.info("Starting WaterBot")

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        # Validate configuration
        validate_config()

        # Start scheduler if enabled
        if ENABLE_SCHEDULING:
            logger.info("Starting device scheduler")
            scheduler.start_scheduler()

        # Create and start the bot
        bot = WaterBot()
        # Store reference for signal handler
        handle_shutdown.bot = bot  # type: ignore[attr-defined]

        bot.start_bot()

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Error in main loop: {e}", exc_info=True)
    finally:
        if "bot" in locals():
            bot.stop_bot()
        scheduler.stop_scheduler()
        gpio_handler.cleanup()
        logger.info("WaterBot shut down")


if __name__ == "__main__":
    main()
