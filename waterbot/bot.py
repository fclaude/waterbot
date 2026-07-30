#!/usr/bin/env python3
"""Main bot entry point for WaterBot."""

import logging
import signal
import sys
import time
from typing import Any, Optional

from . import scheduler
from .config import DEBUG_MODE, ENABLE_SCHEDULING, ENABLE_WEB_INTERFACE, LOG_LEVEL, validate_config
from .discord.bot import WaterBot
from .gpio import handler as gpio_handler
from .web.server import WebInterfaceServer

logger = logging.getLogger("waterbot")

# Restart policy for Discord connectivity failures.
_INITIAL_RESTART_DELAY_SECONDS = 5
_MAX_RESTART_DELAY_SECONDS = 300
_MAX_CONSECUTIVE_FAILURES = 20


def _configure_logging() -> None:
    """Configure application logging once at startup."""
    log_level = getattr(logging, LOG_LEVEL, logging.INFO)
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(log_level)
    else:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler(), logging.FileHandler("waterbot.log")],
        )

    logger.setLevel(logging.DEBUG if DEBUG_MODE else log_level)
    if DEBUG_MODE:
        logging.getLogger("discord_bot").setLevel(logging.DEBUG)

    logger.debug("Logging initialized with level=%s, debug_mode=%s", LOG_LEVEL, DEBUG_MODE)


def handle_shutdown(signum: int, frame: Any) -> None:
    """Handle shutdown signals."""
    logger.info("Received shutdown signal")
    bot = getattr(handle_shutdown, "bot", None)
    if bot is not None:
        bot.stop_bot()
    web_server = getattr(handle_shutdown, "web_server", None)
    if web_server is not None:
        web_server.stop()
    scheduler.stop_scheduler()
    gpio_handler.cleanup()
    sys.exit(0)


def main() -> None:
    """Start the WaterBot application."""
    _configure_logging()
    logger.info("Starting WaterBot")

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        validate_config()
    except ValueError as config_error:
        logger.error("Invalid configuration: %s", config_error)
        raise SystemExit(1) from config_error

    scheduler_started = False
    web_server: Optional[WebInterfaceServer] = None
    restart_delay = _INITIAL_RESTART_DELAY_SECONDS
    consecutive_failures = 0
    bot: Optional[WaterBot] = None

    while True:
        try:
            if not scheduler_started:
                if ENABLE_SCHEDULING:
                    logger.info("Starting device scheduler")
                    scheduler.start_scheduler()
                else:
                    logger.info("Scheduling is disabled")
                scheduler_started = True

            if ENABLE_WEB_INTERFACE and web_server is None:
                logger.info("Starting web interface")
                web_server = WebInterfaceServer()
                web_server.start()
                handle_shutdown.web_server = web_server  # type: ignore[attr-defined]

            logger.info("Starting Discord bot...")
            bot = WaterBot()
            handle_shutdown.bot = bot  # type: ignore[attr-defined]
            bot.start_bot()
            # start_bot blocks until disconnect; treat clean return as success reset.
            consecutive_failures = 0
            restart_delay = _INITIAL_RESTART_DELAY_SECONDS

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            break
        except ValueError as config_error:
            # Configuration mistakes should not restart forever.
            logger.error("Configuration error: %s", config_error)
            raise SystemExit(1) from config_error
        except Exception as exc:
            consecutive_failures += 1
            logger.error("Discord bot crashed: %s", exc, exc_info=True)

            if bot is not None:
                try:
                    bot.stop_bot()
                except Exception as cleanup_error:
                    logger.error("Error during bot cleanup: %s", cleanup_error)
                bot = None

            if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                logger.error(
                    "Reached %s consecutive Discord failures; exiting",
                    _MAX_CONSECUTIVE_FAILURES,
                )
                raise SystemExit(1) from exc

            logger.info(
                "Restarting Discord bot in %s seconds (failure %s/%s)...",
                restart_delay,
                consecutive_failures,
                _MAX_CONSECUTIVE_FAILURES,
            )
            time.sleep(restart_delay)
            restart_delay = min(restart_delay * 2, _MAX_RESTART_DELAY_SECONDS)
            continue

    logger.info("Shutting down WaterBot")
    if bot is not None:
        bot.stop_bot()
    if web_server is not None:
        web_server.stop()
    scheduler.stop_scheduler()
    gpio_handler.cleanup()
    logger.info("WaterBot shut down")


if __name__ == "__main__":
    main()
