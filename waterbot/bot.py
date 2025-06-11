#!/usr/bin/env python3
"""Main bot entry point for WaterBot."""
import logging
import signal
import sys
import time

from . import scheduler
from .config import DEBUG_MODE, ENABLE_SCHEDULING, LOG_LEVEL, validate_config
from .gpio import handler as gpio_handler
from .signal.bot import WaterBot

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
    # Also set DEBUG level for all signalbot loggers
    logging.getLogger("signalbot").setLevel(logging.DEBUG)

logger.debug("Logging initialized with level=%s, debug_mode=%s", LOG_LEVEL, DEBUG_MODE)


def handle_shutdown(signum, frame):
    """Handle shutdown signals."""
    logger.info("Received shutdown signal")
    if hasattr(handle_shutdown, "bot") and handle_shutdown.bot:
        handle_shutdown.bot.stop()
    scheduler.stop_scheduler()
    sys.exit(0)


def main():
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
        handle_shutdown.bot = bot  # Store reference for signal handler

        bot.start()

        # Keep the main thread alive
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Error in main loop: {e}", exc_info=True)
    finally:
        if "bot" in locals():
            bot.stop()
        scheduler.stop_scheduler()
        gpio_handler.cleanup()
        logger.info("WaterBot shut down")


if __name__ == "__main__":
    main()
