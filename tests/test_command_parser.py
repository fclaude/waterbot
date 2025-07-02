"""Tests for command parser functionality."""

from unittest.mock import patch

from waterbot.utils.command_parser import parse_command


class TestCommandParser:
    """Test cases for command parser."""

    def test_status_command(self):
        """Test parsing status command."""
        command_type, params = parse_command("status")

        assert command_type == "status"
        assert params == {}

    def test_status_command_with_whitespace(self):
        """Test parsing status command with extra whitespace."""
        command_type, params = parse_command("  STATUS  ")

        assert command_type == "status"
        assert params == {}

    def test_show_schedules_command(self):
        """Test parsing schedules command variations."""
        for cmd in ["schedules", "schedule", "SCHEDULES", "  schedule  "]:
            command_type, params = parse_command(cmd)

            assert command_type == "show_schedules"
            assert params == {}

    @patch(
        "waterbot.utils.command_parser.DEVICE_TO_PIN",
        {"bed1": 17, "bed2": 18, "bed3": 19},
    )
    def test_show_device_schedules_command(self):
        """Test parsing device-specific schedules command."""
        # Test various formats
        test_cases = [
            ("schedule for bed2", {"device": "bed2"}),
            ("schedules for bed1", {"device": "bed1"}),
            ("SCHEDULE FOR BED3", {"device": "bed3"}),
            ("  schedules  for  bed2  ", {"device": "bed2"}),
        ]

        for cmd, expected_params in test_cases:
            command_type, params = parse_command(cmd)
            assert command_type == "show_device_schedules"
            assert params == expected_params

    @patch("waterbot.utils.command_parser.DEVICE_TO_PIN", {"bed1": 17, "bed2": 18})
    def test_show_device_schedules_unknown_device(self):
        """Test parsing device-specific schedules with unknown device."""
        command_type, params = parse_command("schedule for unknown_device")

        assert command_type == "error"
        assert "Unknown device: unknown_device" in params["message"]

    @patch("waterbot.utils.command_parser.DEVICE_TO_PIN", {"pump": 17, "light": 18})
    def test_schedule_add_command(self):
        """Test parsing schedule add commands."""
        command_type, params = parse_command("schedule pump on 08:00")

        assert command_type == "schedule_add"
        assert params == {"device": "pump", "action": "on", "time": "08:00"}

        command_type, params = parse_command("schedule light off 22:00")

        assert command_type == "schedule_add"
        assert params == {"device": "light", "action": "off", "time": "22:00"}

    @patch("waterbot.utils.command_parser.DEVICE_TO_PIN", {"pump": 17})
    def test_schedule_add_unknown_device(self):
        """Test parsing schedule add with unknown device."""
        command_type, params = parse_command("schedule unknown on 08:00")

        assert command_type == "error"
        assert "Unknown device: unknown" in params["message"]

    @patch("waterbot.utils.command_parser.DEVICE_TO_PIN", {"pump": 17})
    def test_schedule_remove_command(self):
        """Test parsing schedule remove commands."""
        command_type, params = parse_command("unschedule pump on 08:00")

        assert command_type == "schedule_remove"
        assert params == {"device": "pump", "action": "on", "time": "08:00"}

        command_type, params = parse_command("unschedule pump off 20:00")

        assert command_type == "schedule_remove"
        assert params == {"device": "pump", "action": "off", "time": "20:00"}

    @patch("waterbot.utils.command_parser.DEVICE_TO_PIN", {"pump": 17})
    def test_schedule_remove_unknown_device(self):
        """Test parsing schedule remove with unknown device."""
        command_type, params = parse_command("unschedule unknown on 08:00")

        assert command_type == "error"
        assert "Unknown device: unknown" in params["message"]

    def test_all_devices_commands(self):
        """Test parsing all devices on/off commands."""
        command_type, params = parse_command("on all")
        assert command_type == "all_on"
        assert params["timeout"] == 600  # 10 minutes * 60 seconds

        command_type, params = parse_command("off all")
        assert command_type == "all_off"
        assert params["timeout"] == 600  # 10 minutes * 60 seconds

        command_type, params = parse_command("ON ALL")
        assert command_type == "all_on"
        assert params["timeout"] == 600  # 10 minutes * 60 seconds

    @patch("waterbot.utils.command_parser.DEVICE_TO_PIN", {"pump": 17, "light": 18})
    def test_device_on_command(self):
        """Test parsing device on commands."""
        command_type, params = parse_command("on pump")

        assert command_type == "device_on"
        assert params["device"] == "pump"
        assert params["timeout"] == 600  # 10 minutes * 60 seconds

    @patch("waterbot.utils.command_parser.DEVICE_TO_PIN", {"pump": 17})
    def test_device_on_with_timeout(self):
        """Test parsing device on commands with timeout."""
        command_type, params = parse_command("on pump 60")

        assert command_type == "device_on"
        assert params == {"device": "pump", "timeout": 3600}  # 60 minutes * 60 seconds

    @patch("waterbot.utils.command_parser.DEVICE_TO_PIN", {"pump": 17})
    def test_device_on_unknown_device(self):
        """Test parsing device on command with unknown device."""
        command_type, params = parse_command("on unknown")

        assert command_type == "error"
        assert "Unknown device: unknown" in params["message"]

    @patch("waterbot.utils.command_parser.DEVICE_TO_PIN", {"pump": 17, "light": 18})
    def test_device_off_command(self):
        """Test parsing device off commands."""
        command_type, params = parse_command("off light")

        assert command_type == "device_off"
        assert params["device"] == "light"
        assert params["timeout"] == 600  # 10 minutes * 60 seconds

    @patch("waterbot.utils.command_parser.DEVICE_TO_PIN", {"pump": 17})
    def test_device_off_with_timeout(self):
        """Test parsing device off commands with timeout."""
        command_type, params = parse_command("off pump 30")

        assert command_type == "device_off"
        assert params == {"device": "pump", "timeout": 1800}  # 30 minutes * 60 seconds

    @patch("waterbot.utils.command_parser.DEVICE_TO_PIN", {"pump": 17})
    def test_device_off_unknown_device(self):
        """Test parsing device off command with unknown device."""
        command_type, params = parse_command("off unknown")

        assert command_type == "error"
        assert "Unknown device: unknown" in params["message"]

    def test_help_command(self):
        """Test parsing unknown commands returns help."""
        command_type, params = parse_command("unknown command")

        assert command_type == "help"
        assert params == {}

        command_type, params = parse_command("invalid")

        assert command_type == "help"
        assert params == {}

    def test_case_insensitive_parsing(self):
        """Test that command parsing is case insensitive."""
        with patch("waterbot.utils.command_parser.DEVICE_TO_PIN", {"pump": 17}):
            # Test various case combinations
            test_cases = [
                ("ON PUMP", "device_on"),
                ("Off Pump", "device_off"),
                ("STATUS", "status"),
                ("Schedule PUMP on 08:00", "schedule_add"),
                ("UNSCHEDULE pump OFF 20:00", "schedule_remove"),
            ]

            for command, expected_type in test_cases:
                command_type, params = parse_command(command)
                assert command_type == expected_type

    def test_whitespace_handling(self):
        """Test that extra whitespace is handled correctly."""
        with patch("waterbot.utils.command_parser.DEVICE_TO_PIN", {"pump": 17}):
            # Test with extra spaces
            command_type, params = parse_command("   on   pump   60   ")

            assert command_type == "device_on"
            assert params == {
                "device": "pump",
                "timeout": 3600,
            }  # 60 minutes * 60 seconds

    def test_schedule_time_format_validation(self):
        """Test that schedule commands validate time format."""
        with patch("waterbot.utils.command_parser.DEVICE_TO_PIN", {"pump": 17}):
            # Valid time format
            command_type, params = parse_command("schedule pump on 08:30")
            assert command_type == "schedule_add"

            # Invalid time formats should not match schedule pattern
            command_type, params = parse_command("schedule pump on 8:30")  # Missing leading zero
            assert command_type == "help"  # Should fall through to help

            command_type, params = parse_command("schedule pump on 25:00")  # Invalid hour
            assert command_type == "help"  # Should fall through to help

            # Test unschedule time validation too
            command_type, params = parse_command("unschedule pump on 25:00")
            assert command_type == "help"

            command_type, params = parse_command("unschedule pump on 12:75")
            assert command_type == "help"
