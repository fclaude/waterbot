import json
from unittest.mock import Mock, patch

from waterbot.signal.bot import WaterBot


class TestWaterBot:
    """Test cases for WaterBot Signal integration"""

    def setup_method(self):
        """Setup test fixtures"""
        with patch("waterbot.signal.bot.SignalCli"):
            self.bot = WaterBot()

    def test_bot_initialization(self):
        """Test bot initialization"""
        assert self.bot.phone_number == self.bot.phone_number
        assert self.bot.group_id == self.bot.group_id
        assert self.bot.running is False
        assert self.bot.polling_thread is None

    @patch("subprocess.run")
    def test_send_message_to_group(self, mock_run):
        """Test sending message to group"""
        mock_run.return_value.returncode = 0

        success = self.bot._send_message(group_id="test_group", message="test message")

        assert success is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "signal-cli" in call_args
        assert "-g" in call_args
        assert "test_group" in call_args
        assert "test message" in call_args

    @patch("subprocess.run")
    def test_send_message_to_recipient(self, mock_run):
        """Test sending message to individual recipient"""
        mock_run.return_value.returncode = 0

        success = self.bot._send_message(
            recipient="+1234567890", message="test message"
        )

        assert success is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "+1234567890" in call_args
        assert "test message" in call_args

    @patch("subprocess.run")
    def test_send_message_failure(self, mock_run):
        """Test send message failure handling"""
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "Error message"

        success = self.bot._send_message(group_id="test_group", message="test message")

        assert success is False

    def test_send_empty_message(self):
        """Test sending empty message"""
        success = self.bot._send_message(group_id="test_group", message="")

        assert success is False

    @patch("subprocess.run")
    def test_receive_messages(self, mock_run):
        """Test receiving messages"""
        mock_messages = ['{"message": "test1"}', '{"message": "test2"}']
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "\n".join(mock_messages)

        messages = self.bot._receive_messages()

        assert len(messages) == 2
        assert messages == mock_messages

    @patch("subprocess.run")
    def test_receive_messages_empty(self, mock_run):
        """Test receiving no messages"""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""

        messages = self.bot._receive_messages()

        assert messages == []

    @patch("subprocess.run")
    def test_receive_messages_failure(self, mock_run):
        """Test receive messages failure"""
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "Error"

        messages = self.bot._receive_messages()

        assert messages == []

    def test_execute_command_status(self):
        """Test executing status command"""
        with patch("waterbot.signal.bot.gpio_handler.get_status") as mock_get_status:
            mock_get_status.return_value = {"pump": True, "light": False}

            response = self.bot._execute_command("status", {})

            assert "Device Status:" in response
            assert "pump: ON" in response
            assert "light: OFF" in response

    def test_execute_command_device_on(self):
        """Test executing device on command"""
        with patch("waterbot.signal.bot.gpio_handler.turn_on") as mock_turn_on:
            mock_turn_on.return_value = True

            response = self.bot._execute_command(
                "device_on", {"device": "pump", "timeout": None}
            )

            assert "Device 'pump' turned ON" in response
            mock_turn_on.assert_called_once_with("pump", None)

    def test_execute_command_device_on_with_timeout(self):
        """Test executing device on command with timeout"""
        with patch("waterbot.signal.bot.gpio_handler.turn_on") as mock_turn_on:
            mock_turn_on.return_value = True

            response = self.bot._execute_command(
                "device_on", {"device": "pump", "timeout": 3600}
            )

            assert "Device 'pump' turned ON for 3600 seconds" in response
            mock_turn_on.assert_called_once_with("pump", 3600)

    def test_execute_command_device_off(self):
        """Test executing device off command"""
        with patch("waterbot.signal.bot.gpio_handler.turn_off") as mock_turn_off:
            mock_turn_off.return_value = True

            response = self.bot._execute_command(
                "device_off", {"device": "light", "timeout": None}
            )

            assert "Device 'light' turned OFF" in response
            mock_turn_off.assert_called_once_with("light", None)

    def test_execute_command_all_on(self):
        """Test executing all devices on command"""
        with patch("waterbot.signal.bot.gpio_handler.turn_all_on") as mock_turn_all_on:
            mock_turn_all_on.return_value = True

            response = self.bot._execute_command("all_on", {})

            assert "All devices turned ON" in response
            mock_turn_all_on.assert_called_once()

    def test_execute_command_all_off(self):
        """Test executing all devices off command"""
        with patch(
            "waterbot.signal.bot.gpio_handler.turn_all_off"
        ) as mock_turn_all_off:
            mock_turn_all_off.return_value = True

            response = self.bot._execute_command("all_off", {})

            assert "All devices turned OFF" in response
            mock_turn_all_off.assert_called_once()

    def test_execute_command_schedule_add(self):
        """Test executing schedule add command"""
        with patch("waterbot.signal.bot.scheduler.add_schedule") as mock_add_schedule:
            mock_add_schedule.return_value = True

            response = self.bot._execute_command(
                "schedule_add", {"device": "pump", "action": "on", "time": "08:00"}
            )

            assert "Added schedule: pump on at 08:00" in response
            mock_add_schedule.assert_called_once_with("pump", "on", "08:00")

    def test_execute_command_schedule_remove(self):
        """Test executing schedule remove command"""
        with patch(
            "waterbot.signal.bot.scheduler.remove_schedule"
        ) as mock_remove_schedule:
            mock_remove_schedule.return_value = True

            response = self.bot._execute_command(
                "schedule_remove", {"device": "pump", "action": "on", "time": "08:00"}
            )

            assert "Removed schedule: pump on at 08:00" in response
            mock_remove_schedule.assert_called_once_with("pump", "on", "08:00")

    def test_execute_command_show_schedules(self):
        """Test executing show schedules command"""
        mock_schedules = {"pump": {"on": ["08:00"], "off": ["20:00"]}}
        mock_next_runs = [
            {
                "device": "pump",
                "action": "on",
                "time": "08:00",
                "next_run": "2024-01-01 08:00:00",
            }
        ]

        with patch("waterbot.signal.bot.get_schedules") as mock_get_schedules:
            with patch(
                "waterbot.signal.bot.scheduler.get_next_runs"
            ) as mock_get_next_runs:
                mock_get_schedules.return_value = mock_schedules
                mock_get_next_runs.return_value = mock_next_runs

                response = self.bot._execute_command("show_schedules", {})

                assert "Device Schedules:" in response
                assert "PUMP:" in response
                assert "ON at 08:00" in response
                assert "OFF at 20:00" in response
                assert "Next scheduled runs:" in response

    def test_execute_command_show_schedules_empty(self):
        """Test executing show schedules command with no schedules"""
        with patch("waterbot.signal.bot.get_schedules") as mock_get_schedules:
            mock_get_schedules.return_value = {}

            response = self.bot._execute_command("show_schedules", {})

            assert "No schedules configured" in response

    def test_execute_command_help(self):
        """Test executing help command"""
        response = self.bot._execute_command("help", {})

        assert "Available commands:" in response
        assert "status" in response
        assert "on <device>" in response
        assert "schedule" in response

    def test_execute_command_error(self):
        """Test executing error command"""
        response = self.bot._execute_command("error", {"message": "Test error"})

        assert response == "Test error"

    def test_execute_command_unknown(self):
        """Test executing unknown command"""
        response = self.bot._execute_command("unknown", {})

        assert "Unknown command" in response

    def test_handle_message_group_message(self):
        """Test handling a group message"""
        message_json = {
            "envelope": {
                "sourceNumber": "+1234567890",
                "dataMessage": {
                    "groupInfo": {"groupId": self.bot.group_id},
                    "message": "status",
                },
            }
        }

        with patch.object(self.bot, "_execute_command") as mock_execute:
            with patch.object(self.bot, "_send_message") as mock_send:
                mock_execute.return_value = "Test response"

                self.bot._handle_message(json.dumps(message_json))

                mock_execute.assert_called_once()
                mock_send.assert_called_once_with(
                    group_id=self.bot.group_id, message="Test response"
                )

    def test_handle_message_direct_message(self):
        """Test handling a direct message"""
        message_json = {
            "envelope": {
                "sourceNumber": "+1234567890",
                "dataMessage": {"message": "status"},
            }
        }

        with patch.object(self.bot, "_execute_command") as mock_execute:
            with patch.object(self.bot, "_send_message") as mock_send:
                mock_execute.return_value = "Test response"

                self.bot._handle_message(json.dumps(message_json))

                mock_execute.assert_called_once()
                mock_send.assert_called_once_with(
                    recipient="+1234567890", message="Test response"
                )

    def test_handle_message_wrong_group(self):
        """Test handling message from wrong group"""
        message_json = {
            "envelope": {
                "sourceNumber": "+1234567890",
                "dataMessage": {
                    "groupInfo": {"groupId": "wrong_group"},
                    "message": "status",
                },
            }
        }

        with patch.object(self.bot, "_execute_command") as mock_execute:
            self.bot._handle_message(json.dumps(message_json))

            mock_execute.assert_not_called()

    def test_handle_message_empty_text(self):
        """Test handling message with empty text"""
        message_json = {
            "envelope": {
                "sourceNumber": "+1234567890",
                "dataMessage": {
                    "groupInfo": {"groupId": self.bot.group_id},
                    "message": "",
                },
            }
        }

        with patch.object(self.bot, "_execute_command") as mock_execute:
            self.bot._handle_message(json.dumps(message_json))

            mock_execute.assert_not_called()

    def test_handle_message_invalid_json(self):
        """Test handling invalid JSON message"""
        with patch.object(self.bot, "_execute_command") as mock_execute:
            self.bot._handle_message("invalid json")

            mock_execute.assert_not_called()

    @patch("subprocess.run")
    def test_check_signal_cli_available(self, mock_run):
        """Test checking if signal-cli is available"""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "signal-cli 0.10.0"

        result = self.bot._check_signal_cli()

        assert result is True
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_check_signal_cli_not_available(self, mock_run):
        """Test checking signal-cli when not available"""
        mock_run.side_effect = FileNotFoundError()

        result = self.bot._check_signal_cli()

        assert result is False

    @patch("threading.Thread")
    def test_start_bot(self, mock_thread):
        """Test starting the bot"""
        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance

        with patch.object(self.bot, "_check_signal_cli", return_value=True):
            with patch.object(self.bot, "_send_message", return_value=True):
                self.bot.start()

                assert self.bot.running is True
                mock_thread.assert_called_once()
                mock_thread_instance.start.assert_called_once()

    def test_start_bot_signal_cli_not_available(self):
        """Test starting bot when signal-cli is not available"""
        with patch.object(self.bot, "_check_signal_cli", return_value=False):
            self.bot.start()

            assert self.bot.running is False

    def test_start_bot_already_running(self):
        """Test starting bot when already running"""
        self.bot.running = True

        with patch.object(self.bot, "_check_signal_cli") as mock_check:
            self.bot.start()

            mock_check.assert_not_called()

    def test_stop_bot(self):
        """Test stopping the bot"""
        self.bot.running = True
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        self.bot.polling_thread = mock_thread

        with patch.object(self.bot.api, "stop_signal") as mock_stop_signal:
            with patch("waterbot.signal.bot.gpio_handler.cleanup") as mock_cleanup:
                self.bot.stop()

                assert self.bot.running is False
                mock_thread.join.assert_called_once_with(timeout=5)
                mock_stop_signal.assert_called_once()
                mock_cleanup.assert_called_once()

    def test_stop_bot_not_running(self):
        """Test stopping bot when not running"""
        self.bot.running = False

        with patch.object(self.bot.api, "stop_signal") as mock_stop_signal:
            self.bot.stop()

            mock_stop_signal.assert_not_called()
