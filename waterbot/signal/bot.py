import json
import logging
import subprocess
import threading
import time

from SignalCliApi import SignalCli

from .. import scheduler
from ..config import (
    DEBUG_MODE,
    LOG_LEVEL,
    SIGNAL_GROUP_ID,
    SIGNAL_PHONE_NUMBER,
    get_schedules,
)
from ..gpio import handler as gpio_handler
from ..utils.command_parser import parse_command

# Configure logging
log_level = getattr(logging, LOG_LEVEL)
logging.basicConfig(
    level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("signal_bot")
if DEBUG_MODE:
    logger.setLevel(logging.DEBUG)


class WaterBot:
    def __init__(self):
        """Initialize the Signal bot for water control"""
        logger.debug(
            f"Initializing WaterBot with SIGNAL_PHONE_NUMBER={SIGNAL_PHONE_NUMBER}"
        )

        # Initialize the SignalCli with the configured phone number
        self.api = SignalCli(SIGNAL_PHONE_NUMBER)
        self.phone_number = SIGNAL_PHONE_NUMBER
        self.group_id = SIGNAL_GROUP_ID
        logger.debug(f"WaterBot will listen to group ID: {self.group_id}")
        self.running = False
        self.polling_thread = None

        logger.info(f"Signal bot initialized with phone number {SIGNAL_PHONE_NUMBER}")

    def _send_message(self, recipient=None, group_id=None, message=""):
        """
        Send a message using signal-cli command line

        Args:
            recipient: Phone number to send to
            group_id: Group ID to send to
            message: Message text
        """
        if not message:
            logger.warning("Attempted to send empty message")
            return False

        try:
            cmd = ["signal-cli", "-u", self.phone_number]

            if group_id:
                cmd.extend(["send", "-g", group_id])
            elif recipient:
                cmd.extend(["send", recipient])
            else:
                logger.error("No recipient or group specified for message")
                return False

            cmd.extend(["-m", message])

            logger.debug(f"Sending message command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            if result.returncode == 0:
                logger.debug("Message sent successfully")
                return True
            else:
                logger.error(f"Error sending message: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Exception sending message: {e}", exc_info=True)
            return False

    def _receive_messages(self):
        """
        Receive messages using signal-cli command line

        Returns:
            List of message JSON strings
        """
        try:
            cmd = ["signal-cli", "-u", self.phone_number, "-o", "json", "receive"]

            logger.debug(f"Receiving messages command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            if result.returncode == 0:
                if result.stdout.strip():
                    # Split by newlines, each line is a JSON message
                    messages = [msg for msg in result.stdout.strip().split("\n") if msg]
                    logger.debug(f"Received {len(messages)} messages")
                    return messages
                return []
            else:
                logger.error(f"Error receiving messages: {result.stderr}")
                return []
        except Exception as e:
            logger.error(f"Exception receiving messages: {e}", exc_info=True)
            return []

    def _poll_messages(self):
        """Poll for new messages in a separate thread"""
        logger.debug("Starting message polling thread")

        while self.running:
            try:
                # Check for new messages
                messages = self._receive_messages()
                if messages:
                    for message in messages:
                        self._handle_message(message)
            except Exception as e:
                logger.error(f"Error polling messages: {e}", exc_info=True)

            # Sleep before next poll
            time.sleep(2)

        logger.debug("Message polling thread stopped")

    def _handle_message(self, message):
        """
        Handle incoming Signal messages

        Args:
            message: JSON message string from SignalCliApi
        """
        try:
            logger.debug(f"Received message: {message}")

            # Parse the message JSON
            try:
                message_data = json.loads(message)

                # The structure depends on how signal-cli formats its JSON output
                envelope = message_data.get("envelope", {})
                data_message = envelope.get("dataMessage", {})

                source = envelope.get("sourceNumber", envelope.get("source", "Unknown"))
                group_id = data_message.get("groupInfo", {}).get("groupId")
                text = data_message.get("message", "")

                # Check if this is a group message and if it's from our target group
                if group_id:
                    logger.debug(f"Message from group: {group_id}")
                    if group_id != self.group_id:
                        logger.debug(
                            "Group ID mismatch. Ignoring message from different group."
                        )
                        return
                else:
                    # Process direct messages as well for easier testing
                    logger.debug("Processing direct message")

                # Get the message text
                if not text or not text.strip():
                    logger.debug("Message has no text, ignoring")
                    return

                text = text.strip().lower()
                logger.info(f"Received command: {text}")

                # Process the command using the command parser
                command_type, params = parse_command(text)
                response = self._execute_command(command_type, params)

                if response:
                    logger.debug(f"Sending response: {response}")
                    # Send the response
                    if group_id:
                        self._send_message(group_id=self.group_id, message=response)
                    else:
                        self._send_message(recipient=source, message=response)
                else:
                    logger.debug("No response to send")
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing message JSON: {e}")
                return

        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)

    def _execute_command(self, command_type, params):
        """
        Execute a parsed command

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
                time_msg = f" for {timeout} seconds" if timeout else ""
                return f"Device '{device}' turned ON{time_msg}"
            else:
                return f"Error: Unknown device '{device}'"

        elif command_type == "device_off":
            device = params["device"]
            timeout = params.get("timeout")
            success = gpio_handler.turn_off(device, timeout)
            if success:
                time_msg = f" for {timeout} seconds" if timeout else ""
                return f"Device '{device}' turned OFF{time_msg}"
            else:
                return f"Error: Unknown device '{device}'"

        elif command_type == "error":
            return params["message"]

        elif command_type == "help":
            return self._get_help_response()

        else:
            return "Unknown command. Send 'help' for available commands."

    def _get_help_response(self):
        """Generate help response message"""
        return (
            "Available commands:\n"
            "status - Show status of all devices\n"
            "on <device> [time] - Turn on a device\n"
            "off <device> [time] - Turn off a device\n"
            "on all - Turn on all devices\n"
            "off all - Turn off all devices\n"
            "schedules - Show all schedules\n"
            "schedule <device> <on|off> <HH:MM> - Add schedule\n"
            "unschedule <device> <on|off> <HH:MM> - Remove schedule"
        )

    def _get_schedules_response(self):
        """Generate schedules response message"""
        schedules = get_schedules()
        if not schedules:
            return "No schedules configured"

        response = "Device Schedules:\n"
        for device, actions in schedules.items():
            response += f"\n{device.upper()}:\n"
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

        return response

    def _get_status_response(self):
        """
        Generate status response message

        Returns:
            str: Status message
        """
        status = gpio_handler.get_status()
        if not status:
            return "No devices configured"

        response = "Device Status:\n"
        for device, is_on in status.items():
            status_text = "ON" if is_on else "OFF"
            response += f"- {device}: {status_text}\n"

        return response

    def start(self):
        """Start the Signal bot"""
        if self.running:
            logger.warning("Bot is already running")
            return

        logger.info("Starting Signal bot")
        try:
            # Check if signal-cli is installed
            if not self._check_signal_cli():
                logger.error("signal-cli is not installed or not in PATH")
                return

            self.running = True

            # Start polling thread
            self.polling_thread = threading.Thread(target=self._poll_messages)
            self.polling_thread.daemon = True
            self.polling_thread.start()

            # Send startup message
            try:
                startup_message = (
                    'WaterBot is now online! 💧\nSend "status" to check device status.'
                )
                logger.debug(f"Sending startup message to group {self.group_id}")
                success = self._send_message(
                    group_id=self.group_id, message=startup_message
                )
                if success:
                    logger.info("Startup message sent successfully")
                else:
                    logger.warning("Failed to send startup message")
            except Exception as e:
                logger.error(f"Error sending startup message: {e}", exc_info=True)

        except Exception as e:
            self.running = False
            logger.error(f"Error starting bot: {e}", exc_info=True)
            raise

    def _check_signal_cli(self):
        """Check if signal-cli is installed and in PATH"""
        try:
            result = subprocess.run(
                ["signal-cli", "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode == 0:
                logger.debug(f"signal-cli version: {result.stdout.strip()}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error checking signal-cli: {e}")
            return False

    def stop(self):
        """Stop the Signal bot"""
        if not self.running:
            logger.warning("Bot is not running")
            return

        logger.info("Stopping Signal bot")
        self.running = False

        # Join polling thread
        if self.polling_thread and self.polling_thread.is_alive():
            self.polling_thread.join(timeout=5)

        # Stop SignalCli
        self.api.stop_signal()

        # Clean up GPIO
        gpio_handler.cleanup()
        logger.info("Bot stopped")
