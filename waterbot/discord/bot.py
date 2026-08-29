"""Discord bot implementation for WaterBot."""

import logging
from typing import Any, Optional, cast

import discord
from discord.ext import commands

from ..actions import ActionEngine
from ..agent.routing import try_direct_command
from ..config import (
    DEBUG_MODE,
    DISCORD_BOT_TOKEN,
    DISCORD_CHANNEL_ID,
    LOG_LEVEL,
    is_openai_configured,
)
from ..gpio import handler as gpio_handler
from ..openai_integration import process_with_openai
from ..services import get_action_engine, get_agent_memory
from ..utils.command_parser import parse_command

logger = logging.getLogger("discord_bot")


def _configure_discord_logging() -> None:
    """Apply Discord logger level without reconfiguring the root logger."""
    log_level = getattr(logging, LOG_LEVEL, logging.INFO)
    logger.setLevel(logging.DEBUG if DEBUG_MODE else log_level)


_configure_discord_logging()


class WaterBot(commands.Bot):
    """Discord bot for controlling water devices via GPIO."""

    help_command = None

    def __init__(self, action_engine: Optional[ActionEngine] = None) -> None:
        """Initialize the Discord bot for water control."""
        logger.debug("Initializing WaterBot Discord bot")

        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents, help_command=None)

        self.channel_id = int(DISCORD_CHANNEL_ID) if DISCORD_CHANNEL_ID else None
        self.target_channel: Optional[discord.abc.Messageable] = None
        self._action_engine = action_engine or get_action_engine()

        set_bot_instance(self)
        logger.info("Discord bot initialized for channel ID: %s", self.channel_id)

    def _get_action_engine(self) -> ActionEngine:
        """Return the shared action engine."""
        return self._action_engine

    async def on_ready(self) -> None:
        """Get called when the bot is ready."""
        logger.info("Discord bot logged in as %s", self.user)

        if not self.channel_id:
            return

        channel = self.get_channel(self.channel_id)
        if channel is None:
            logger.error("Could not find channel with ID: %s", self.channel_id)
            return

        self.target_channel = cast(discord.abc.Messageable, channel)
        channel_name = getattr(channel, "name", str(self.channel_id))
        logger.info("Connected to channel: %s", channel_name)

        ip_result = self._get_action_engine().execute_action(
            "get_ip_addresses",
            {},
            source="discord_startup",
            require_confirmation=False,
        )
        ip_info = ip_result.data.get("ip_info", {})

        startup_message = "WaterBot is now online!\n"
        if is_openai_configured():
            startup_message += "AI-powered conversational interface enabled!\n"
            startup_message += "Just chat with me naturally to control devices.\n\n"
        else:
            startup_message += "Send `status` to check device status.\n"
            startup_message += "Tip: Set OPENAI_API_KEY (and optional OPENAI_BASE_URL) for conversational AI.\n\n"

        if ip_info:
            startup_message += "SSH Access:\n"
            for interface, ip in ip_info.items():
                startup_message += f"- `ssh pi@{ip}` (via {interface})\n"
        else:
            startup_message += "No network interfaces found with IP addresses."

        await self.target_channel.send(startup_message)

    async def on_message(self, message: discord.Message) -> None:
        """Handle incoming Discord messages."""
        if message.author == self.user:
            return

        if self.channel_id and message.channel.id != self.channel_id:
            return

        text = message.content.strip()
        if not text:
            return

        logger.info("Received message: %s", text)
        channel_id = str(message.channel.id)
        author_id = _safe_discord_id(message.author)
        author_name = _safe_discord_name(message.author)

        direct = try_direct_command(
            text,
            action_engine=self._get_action_engine(),
            channel_id=channel_id,
            source="discord_command",
            author_id=author_id,
            author_name=author_name,
            memory=get_agent_memory(),
        )
        if direct is not None:
            await message.channel.send(direct)
            return

        if is_openai_configured():
            try:
                response = await process_with_openai(text, channel_id, author_id, author_name)
                if response:
                    logger.debug("Sending OpenAI response: %s", response)
                    await message.channel.send(response)
                return
            except Exception as exc:
                logger.error("OpenAI processing failed: %s", exc, exc_info=True)

        command_type, params = parse_command(text.lower())
        command_response = await self._execute_command(command_type, params, channel_id=channel_id)
        if command_response:
            logger.debug("Sending response: %s", command_response)
            await message.channel.send(command_response)

    async def _execute_command(
        self,
        command_type: Optional[str],
        params: dict,
        channel_id: Optional[str] = None,
    ) -> Optional[str]:
        """Execute a parsed command through the shared action engine."""
        if command_type == "help" or command_type is None:
            return self._get_help_response()

        if command_type == "error":
            return str(params["message"])

        if command_type == "confirm":
            return self._get_action_engine().confirm(params["token"], channel_id=channel_id).message

        if command_type == "cancel":
            return self._get_action_engine().cancel(params["token"], channel_id=channel_id).message

        # Explicit Discord text commands do not require confirmation tokens.
        result = self._get_action_engine().execute_action(
            command_type,
            params,
            source="discord_command",
            channel_id=channel_id,
            require_confirmation=False,
        )
        return result.message

    def _get_help_response(self) -> str:
        """Generate help response message."""
        return (
            "**Available commands:**\n"
            "```\n"
            "status - Show status of all devices\n"
            "on <device> [minutes] - Turn on a device (permanent unless minutes given)\n"
            "off <device> [minutes] - Turn off a device (permanent unless minutes given)\n"
            "on all [minutes] - Turn on all devices\n"
            "off all [minutes] - Turn off all devices\n"
            "schedules - Show all schedules\n"
            "cycles - Show flexible cycle schedules\n"
            "schedule for <device> - Show schedules for specific device\n"
            "schedule <device> <on|off> <HH:MM> - Add schedule\n"
            "unschedule <device> <on|off> <HH:MM> - Remove schedule\n"
            "cycle <device> every <N> days at <HH:MM> for <minutes> minutes\n"
            "uncycle <policy_id> - Remove flexible cycle schedule\n"
            "confirm <token> - Execute a pending risky action\n"
            "cancel <token> - Cancel a pending risky action\n"
            "why <device> - Explain recent flexible schedule decisions\n"
            "feedback <device> <note> - Record watering feedback\n"
            "time - Show current time on bot node\n"
            "ip - Show SSH access information\n"
            "test - Test notification system\n"
            "```\n"
            + (
                "Tip: Set OPENAI_API_KEY (and optional OPENAI_BASE_URL) for conversational AI."
                if not is_openai_configured()
                else "AI-powered conversational interface enabled!"
            )
        )

    def start_bot(self) -> None:
        """Start the Discord bot."""
        logger.info("Starting Discord bot")
        if not DISCORD_BOT_TOKEN:
            raise ValueError("Discord bot token not configured")
        if not self.channel_id:
            raise ValueError("Discord channel ID not configured")

        logger.info("Attempting to connect to Discord...")
        self.run(DISCORD_BOT_TOKEN)

    def stop_bot(self) -> None:
        """Stop the Discord bot."""
        logger.info("Stopping Discord bot")
        gpio_handler.cleanup()
        logger.info("Bot stopped")


_bot_instance: Optional[WaterBot] = None


def get_bot_instance() -> Optional[WaterBot]:
    """Get the current bot instance for sending notifications."""
    return _bot_instance


def set_bot_instance(bot: WaterBot) -> None:
    """Set the bot instance for notifications."""
    global _bot_instance
    _bot_instance = bot


def _safe_discord_id(author: Any) -> Optional[str]:
    """Return a Discord author ID when available."""
    author_id = getattr(author, "id", None)
    if isinstance(author_id, (int, str)):
        return str(author_id)
    return None


def _safe_discord_name(author: Any) -> Optional[str]:
    """Return a stable Discord author display name when available."""
    for attribute in ("display_name", "global_name", "name"):
        value = getattr(author, attribute, None)
        if isinstance(value, str) and value:
            return value
    name = str(author)
    return name if name else None
