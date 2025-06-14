"""Discord bot implementation for WaterBot."""

import logging
from typing import Optional

import discord
from discord.ext import commands
from discord.ext.commands import Context

from .. import scheduler
from ..config import (
    DEBUG_MODE,
    DISCORD_BOT_TOKEN,
    DISCORD_CHANNEL_ID,
    LOG_LEVEL,
    get_schedules,
)
from ..gpio import handler as gpio_handler
from ..utils.command_parser import parse_command

# Configure logging
log_level = getattr(logging, LOG_LEVEL)
logging.basicConfig(
    level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("discord_bot")
if DEBUG_MODE:
    logger.setLevel(logging.DEBUG)


class WaterBot(commands.Bot):
    """Discord bot for controlling water devices via GPIO."""

    def __init__(self) -> None:
        """Initialize the Discord bot for water control."""
        logger.debug("Initializing WaterBot Discord bot")

        # Initialize bot with command prefix
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

        self.channel_id = int(DISCORD_CHANNEL_ID) if DISCORD_CHANNEL_ID else None
        self.target_channel: Optional[discord.TextChannel] = None

        logger.info(f"Discord bot initialized for channel ID: {self.channel_id}")

    async def on_ready(self) -> None:
        """Get called when the bot is ready."""
        logger.info(f"Discord bot logged in as {self.user}")

        if self.channel_id:
            self.target_channel = self.get_channel(self.channel_id)
            if self.target_channel:
                logger.info(f"Connected to channel: {self.target_channel.name}")
                await self.target_channel.send(
                    "WaterBot is now online! 💧\nSend `status` to check device status."
                )
            else:
                logger.error(f"Could not find channel with ID: {self.channel_id}")

    async def on_message(self, message: discord.Message) -> None:
        """Handle incoming Discord messages."""
        # Ignore messages from the bot itself
        if message.author == self.user:
            return

        # Only process messages from the target channel
        if self.channel_id and message.channel.id != self.channel_id:
            return

        # Process commands that start with !
        if message.content.startswith("!"):
            await self.process_commands(message)
            return

        # Also process plain text commands for backward compatibility
        text = message.content.strip().lower()
        if text:
            logger.info(f"Received command: {text}")

            # Process the command using the command parser
            command_type, params = parse_command(text)
            response = await self._execute_command(command_type, params)

            if response:
                logger.debug(f"Sending response: {response}")
                await message.channel.send(response)

    @commands.command(name="status")
    async def status_command(self, ctx: Context) -> None:
        """Show status of all devices."""
        response = self._get_status_response()
        await ctx.send(response)

    @commands.command(name="schedules")
    async def schedules_command(self, ctx: Context) -> None:
        """Show all device schedules."""
        response = self._get_schedules_response()
        await ctx.send(response)

    @commands.command(name="on")
    async def on_command(
        self, ctx: Context, device: str, timeout: Optional[int] = None
    ) -> None:
        """Turn on a device."""
        if device.lower() == "all":
            gpio_handler.turn_all_on()
            await ctx.send("All devices turned ON")
        else:
            success = gpio_handler.turn_on(device, timeout)
            if success:
                time_msg = f" for {timeout // 60} minutes" if timeout else ""
                await ctx.send(f"Device '{device}' turned ON{time_msg}")
            else:
                await ctx.send(f"Error: Unknown device '{device}'")

    @commands.command(name="off")
    async def off_command(
        self, ctx: Context, device: str, timeout: Optional[int] = None
    ) -> None:
        """Turn off a device."""
        if device.lower() == "all":
            gpio_handler.turn_all_off()
            await ctx.send("All devices turned OFF")
        else:
            success = gpio_handler.turn_off(device, timeout)
            if success:
                time_msg = f" for {timeout // 60} minutes" if timeout else ""
                await ctx.send(f"Device '{device}' turned OFF{time_msg}")
            else:
                await ctx.send(f"Error: Unknown device '{device}'")

    @commands.command(name="schedule")
    async def schedule_command(
        self, ctx: Context, device: str, action: str, time: str
    ) -> None:
        """Add a schedule for a device."""
        success = scheduler.add_schedule(device, action, time)
        if success:
            await ctx.send(f"Added schedule: {device} {action} at {time}")
        else:
            await ctx.send(f"Failed to add schedule for {device}")

    @commands.command(name="unschedule")
    async def unschedule_command(
        self, ctx: Context, device: str, action: str, time: str
    ) -> None:
        """Remove a schedule for a device."""
        success = scheduler.remove_schedule(device, action, time)
        if success:
            await ctx.send(f"Removed schedule: {device} {action} at {time}")
        else:
            await ctx.send(f"No such schedule found: {device} {action} at {time}")

    @commands.command(name="help")
    async def help_command(self, ctx: Context) -> None:
        """Show help message."""
        response = self._get_help_response()
        await ctx.send(response)

    async def _execute_command(
        self, command_type: Optional[str], params: dict
    ) -> Optional[str]:
        """Execute a parsed command.

        Args:
            command_type (str): Type of command
            params (dict): Command parameters

        Returns:
            str: Response message
        """
        if command_type == "status":
            return self._get_status_response()

        elif command_type == "show_schedules":
            return self._get_schedules_response()

        elif command_type == "schedule_add":
            device = params["device"]
            action = params["action"]
            time_str = params["time"]
            success = scheduler.add_schedule(device, action, time_str)
            if success:
                return f"Added schedule: {device} {action} at {time_str}"
            else:
                return f"Failed to add schedule for {device}"

        elif command_type == "schedule_remove":
            device = params["device"]
            action = params["action"]
            time_str = params["time"]
            success = scheduler.remove_schedule(device, action, time_str)
            if success:
                return f"Removed schedule: {device} {action} at {time_str}"
            else:
                return f"No such schedule found: {device} {action} at {time_str}"

        elif command_type == "all_on":
            gpio_handler.turn_all_on()
            return "All devices turned ON"

        elif command_type == "all_off":
            gpio_handler.turn_all_off()
            return "All devices turned OFF"

        elif command_type == "device_on":
            device = params["device"]
            timeout = params.get("timeout")
            success = gpio_handler.turn_on(device, timeout)
            if success:
                time_msg = f" for {timeout // 60} minutes" if timeout else ""
                return f"Device '{device}' turned ON{time_msg}"
            else:
                return f"Error: Unknown device '{device}'"

        elif command_type == "device_off":
            device = params["device"]
            timeout = params.get("timeout")
            success = gpio_handler.turn_off(device, timeout)
            if success:
                time_msg = f" for {timeout // 60} minutes" if timeout else ""
                return f"Device '{device}' turned OFF{time_msg}"
            else:
                return f"Error: Unknown device '{device}'"

        elif command_type == "error":
            return str(params["message"])

        elif command_type == "help":
            return self._get_help_response()

        else:
            return "Unknown command. Send 'help' for available commands."

    def _get_help_response(self) -> str:
        """Generate help response message."""
        return (
            "Available commands:\n"
            "```\n"
            "status - Show status of all devices\n"
            "on <device> [minutes] - Turn on a device\n"
            "off <device> [minutes] - Turn off a device\n"
            "on all - Turn on all devices\n"
            "off all - Turn off all devices\n"
            "schedules - Show all schedules\n"
            "schedule <device> <on|off> <HH:MM> - Add schedule\n"
            "unschedule <device> <on|off> <HH:MM> - Remove schedule\n"
            "```"
        )

    def _get_schedules_response(self) -> str:
        """Generate schedules response message."""
        schedules = get_schedules()
        if not schedules:
            return "No schedules configured"

        response = "**Device Schedules:**\n```\n"
        for device, actions in schedules.items():
            response += f"{device.upper()}:\n"
            for action, times in actions.items():
                for time_str in times:
                    response += f"  {action.upper()} at {time_str}\n"

        # Add next runs information
        next_runs = scheduler.get_next_runs()
        if next_runs:
            response += "\nNext scheduled runs:\n"
            for run in next_runs[:5]:  # Show next 5 runs
                response += (
                    f"  {run['device']} {run['action']} at {run['time']} "
                    f"(next: {run['next_run']})\n"
                )

        response += "```"
        return response

    def _get_status_response(self) -> str:
        """Generate status response message.

        Returns:
            str: Status message
        """
        status = gpio_handler.get_status()
        if not status:
            return "No devices configured"

        response = "**Device Status:**\n```\n"
        for device, is_on in status.items():
            status_text = "ON" if is_on else "OFF"
            response += f"- {device}: {status_text}\n"

        response += "```"
        return response

    def start_bot(self) -> None:
        """Start the Discord bot."""
        logger.info("Starting Discord bot")
        try:
            self.run(DISCORD_BOT_TOKEN)
        except Exception as e:
            logger.error(f"Error starting Discord bot: {e}", exc_info=True)
            raise

    def stop_bot(self) -> None:
        """Stop the Discord bot."""
        logger.info("Stopping Discord bot")
        # Clean up GPIO
        gpio_handler.cleanup()
        logger.info("Bot stopped")
