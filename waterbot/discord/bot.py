"""Discord bot implementation for WaterBot."""

import logging
import subprocess  # nosec B404
from typing import Dict, Optional

import discord
from discord.ext import commands

from .. import scheduler
from ..config import (
    DEBUG_MODE,
    DISCORD_BOT_TOKEN,
    DISCORD_CHANNEL_ID,
    LOG_LEVEL,
    OPENAI_API_KEY,
    get_schedules,
)
from ..gpio import handler as gpio_handler
from ..openai_integration import process_with_openai
from ..utils.command_parser import parse_command

# Configure logging
log_level = getattr(logging, LOG_LEVEL)
logging.basicConfig(level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
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

        # Register this bot instance globally for notifications
        set_bot_instance(self)

        logger.info(f"Discord bot initialized for channel ID: {self.channel_id}")

    def _get_ip_addresses(self) -> Dict[str, str]:
        """Get IP addresses for all network interfaces."""
        ip_info = {}
        try:
            # Get all network interfaces except loopback
            result = subprocess.run(["ls", "/sys/class/net/"], capture_output=True, text=True, check=True)  # nosec
            interfaces = [iface for iface in result.stdout.strip().split() if iface != "lo"]

            for interface in interfaces:
                try:
                    # Get IP address for this interface
                    result = subprocess.run(  # nosec
                        ["ip", "addr", "show", interface],
                        capture_output=True,
                        text=True,
                        check=True,
                    )

                    # Parse IP address from output
                    for line in result.stdout.split("\n"):
                        if "inet " in line and "127.0.0.1" not in line:
                            ip = line.strip().split()[1].split("/")[0]
                            if ip:
                                ip_info[interface] = ip
                                break

                except subprocess.CalledProcessError:
                    continue

        except subprocess.CalledProcessError:
            logger.warning("Failed to get network interface information")

        return ip_info

    async def on_ready(self) -> None:
        """Get called when the bot is ready."""
        logger.info(f"Discord bot logged in as {self.user}")

        if self.channel_id:
            self.target_channel = self.get_channel(self.channel_id)
            if self.target_channel:
                logger.info(f"Connected to channel: {self.target_channel.name}")

                # Get IP address information
                ip_info = self._get_ip_addresses()

                startup_message = "WaterBot is now online! 💧\n"
                if OPENAI_API_KEY:
                    startup_message += "🤖 AI-powered conversational interface enabled!\n"
                    startup_message += "Just chat with me naturally to control devices.\n\n"
                else:
                    startup_message += "Send `status` to check device status.\n"
                    startup_message += "💡 Tip: Set OPENAI_API_KEY for conversational AI interface.\n\n"

                if ip_info:
                    startup_message += "📡 **SSH Access:**\n"
                    for interface, ip in ip_info.items():
                        startup_message += f"• `ssh pi@{ip}` (via {interface})\n"
                else:
                    startup_message += "⚠️ No network interfaces found with IP addresses."

                await self.target_channel.send(startup_message)
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

        # Process conversational messages with OpenAI if configured
        text = message.content.strip()
        if text:
            logger.info(f"Received message: {text}")

            if OPENAI_API_KEY:
                # Use OpenAI for conversational interface with tool support
                try:
                    response = await process_with_openai(text)
                    if response:
                        logger.debug(f"Sending OpenAI response: {response}")
                        await message.channel.send(response)
                except Exception as e:
                    logger.error(f"OpenAI processing failed: {e}", exc_info=True)
                    # Fallback to command parser
                    text_lower = text.lower()
                    command_type, params = parse_command(text_lower)
                    response = await self._execute_command(command_type, params)
                    if response:
                        logger.debug(f"Sending fallback response: {response}")
                        await message.channel.send(response)
            else:
                # Fallback to legacy command parser if OpenAI not configured
                text_lower = text.lower()
                command_type, params = parse_command(text_lower)
                response = await self._execute_command(command_type, params)
                if response:
                    logger.debug(f"Sending response: {response}")
                    await message.channel.send(response)

    async def _execute_command(self, command_type: Optional[str], params: dict) -> Optional[str]:
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

        elif command_type == "show_device_schedules":
            device = params["device"]
            return self._get_device_schedules_response(device)

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
                return f"Device '{device}' turned OFF permanently"
            else:
                return f"Error: Unknown device '{device}'"

        elif command_type == "error":
            return str(params["message"])

        elif command_type == "test":
            # Execute test notification
            from .. import scheduler

            scheduler_instance = scheduler.get_scheduler()
            scheduler_instance._send_discord_notification("test_device", "on", True)
            return "💧 **Test Notification** - Test via plain text command completed"

        elif command_type == "time":
            # Execute time command
            from datetime import datetime

            current_time = datetime.now()
            response = f"🕐 **Current Time:** {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"

            # Also show timezone info if available
            try:
                import subprocess  # nosec B404

                tz_result = subprocess.run(  # nosec B603, B607
                    ["timedatectl", "show", "--property=Timezone", "--value"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if tz_result.returncode == 0 and tz_result.stdout.strip():
                    timezone = tz_result.stdout.strip()
                    response += f"\n📍 **Timezone:** {timezone}"
            except (
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
                FileNotFoundError,
            ):
                # timedatectl not available or failed, try alternative
                try:
                    import time

                    response += f"\n📍 **Timezone:** {time.tzname[time.daylight]}"
                except Exception:  # nosec B110
                    pass

            return response

        elif command_type == "ip":
            # Execute ip command
            ip_info = self._get_ip_addresses()

            if ip_info:
                response = "📡 **SSH Access Information:**\n\n"
                for interface, ip in ip_info.items():
                    response += f"• `ssh pi@{ip}` (via {interface})\n"
            else:
                response = "⚠️ No network interfaces found with IP addresses.\n" "Please check your network connection."

            return response

        elif command_type == "help":
            return self._get_help_response()

        else:
            return "Unknown command. Send 'help' for available commands."

    def _get_help_response(self) -> str:
        """Generate help response message."""
        if OPENAI_API_KEY:
            return (
                "🤖 **AI-Powered WaterBot**\n\n"
                "Just chat with me naturally! Try saying:\n"
                "• 'Turn on the pump for 30 minutes'\n"
                "• 'What's the status of all devices?'\n"
                "• 'Schedule the light to turn on at 6:30'\n"
                "• 'What time is it?'\n"
                "• 'Show me the IP address'\n"
                "• 'Turn off all devices'\n\n"
                "I can control your devices, manage schedules, and provide system information "
                "through natural conversation!"
            )
        else:
            return (
                "**Available commands:**\n"
                "```\n"
                "status - Show status of all devices\n"
                "on <device> [minutes] - Turn on a device\n"
                "off <device> [minutes] - Turn off a device\n"
                "on all - Turn on all devices\n"
                "off all - Turn off all devices\n"
                "schedules - Show all schedules\n"
                "schedule for <device> - Show schedules for specific device\n"
                "schedule <device> <on|off> <HH:MM> - Add schedule\n"
                "unschedule <device> <on|off> <HH:MM> - Remove schedule\n"
                "time - Show current time on bot node\n"
                "ip - Show SSH access information\n"
                "test - Test notification system\n"
                "```\n"
                "💡 Tip: Set OPENAI_API_KEY for conversational AI interface."
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
                response += f"  {run['device']} {run['action']} at {run['time']} " f"(next: {run['next_run']})\n"

        response += "```"
        return response

    def _get_device_schedules_response(self, device: str) -> str:
        """Generate schedules response message for a specific device."""
        schedules = get_schedules(device)
        if not schedules:
            return f"No schedules configured for device '{device}'"

        response = f"**Schedules for {device.upper()}:**\n```\n"
        for action, times in schedules.items():
            for time_str in times:
                response += f"  {action.upper()} at {time_str}\n"

        # Add next runs information for this device
        next_runs = scheduler.get_next_runs()
        if next_runs:
            device_runs = [run for run in next_runs if run["device"].lower() == device.lower()]
            if device_runs:
                response += f"\nNext scheduled runs for {device}:\n"
                for run in device_runs[:5]:  # Show next 5 runs for this device
                    response += f"  {run['action']} at {run['time']} (next: {run['next_run']})\n"

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
            if not DISCORD_BOT_TOKEN:
                raise ValueError("Discord bot token not configured")
            if not self.channel_id:
                raise ValueError("Discord channel ID not configured")

            logger.info("Attempting to connect to Discord...")
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


# Global bot instance for notifications
_bot_instance: Optional[WaterBot] = None


def get_bot_instance() -> Optional[WaterBot]:
    """Get the current bot instance for sending notifications."""
    return _bot_instance


def set_bot_instance(bot: WaterBot) -> None:
    """Set the bot instance for notifications."""
    global _bot_instance
    _bot_instance = bot
