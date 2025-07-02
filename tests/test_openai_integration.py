"""Tests for waterbot/openai_integration.py."""

from unittest.mock import MagicMock, patch

import pytest

from waterbot.openai_integration import (
    execute_tool_call,
    get_available_tools,
    process_with_openai,
)


class TestOpenAIIntegration:
    """Test cases for OpenAI integration."""

    def test_get_available_tools(self):
        """Test get_available_tools returns correct structure."""
        tools = get_available_tools()

        assert isinstance(tools, list)
        assert len(tools) > 0

        # Check that each tool has required structure
        for tool in tools:
            assert "type" in tool
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]

    def test_get_available_tools_function_names(self):
        """Test that expected functions are available."""
        tools = get_available_tools()
        function_names = [tool["function"]["name"] for tool in tools]

        expected_functions = [
            "replace_device_schedule",
            "clear_device_schedule",
            "get_device_status",
            "turn_device_on",
            "turn_device_off",
            "add_schedule",
            "remove_schedule",
            "get_schedules",
            "get_current_time",
            "get_ip_addresses",
            "test_notification",
        ]

        for expected_func in expected_functions:
            assert expected_func in function_names

    @patch("waterbot.openai_integration.gpio_handler")
    def test_execute_tool_get_device_status_all(self, mock_gpio_handler):
        """Test execute_tool_call for get_device_status (all devices)."""
        mock_gpio_handler.get_status.return_value = {"pump": True, "light": False}

        result = execute_tool_call("get_device_status", {})

        assert "Device Status:" in result
        assert "pump: ON" in result
        assert "light: OFF" in result

    @patch("waterbot.openai_integration.gpio_handler")
    def test_execute_tool_get_device_status_specific(self, mock_gpio_handler):
        """Test execute_tool_call for get_device_status (specific device)."""
        mock_gpio_handler.get_status.return_value = {"pump": True, "light": False}

        result = execute_tool_call("get_device_status", {"device": "pump"})

        assert "Device 'pump' is ON" in result

    @patch("waterbot.openai_integration.gpio_handler")
    def test_execute_tool_get_device_status_not_found(self, mock_gpio_handler):
        """Test execute_tool_call for get_device_status (device not found)."""
        mock_gpio_handler.get_status.return_value = {"pump": True}

        result = execute_tool_call("get_device_status", {"device": "unknown"})

        assert "Device 'unknown' not found" in result

    @patch("waterbot.openai_integration.gpio_handler")
    def test_execute_tool_get_device_status_no_devices(self, mock_gpio_handler):
        """Test execute_tool_call for get_device_status (no devices)."""
        mock_gpio_handler.get_status.return_value = {}

        result = execute_tool_call("get_device_status", {})

        assert "No devices configured" in result

    @patch("waterbot.openai_integration.gpio_handler")
    def test_execute_tool_turn_device_on(self, mock_gpio_handler):
        """Test execute_tool_call for turn_device_on."""
        mock_gpio_handler.turn_on.return_value = True

        result = execute_tool_call("turn_device_on", {"device": "pump"})

        assert "Device 'pump' turned ON" in result
        mock_gpio_handler.turn_on.assert_called_once_with("pump", None)

    @patch("waterbot.openai_integration.gpio_handler")
    def test_execute_tool_turn_device_on_with_duration(self, mock_gpio_handler):
        """Test execute_tool_call for turn_device_on with duration."""
        mock_gpio_handler.turn_on.return_value = True

        result = execute_tool_call("turn_device_on", {"device": "pump", "duration_minutes": 30})

        assert "Device 'pump' turned ON for 30 minutes" in result
        mock_gpio_handler.turn_on.assert_called_once_with("pump", 1800)  # 30 * 60

    @patch("waterbot.openai_integration.gpio_handler")
    def test_execute_tool_turn_device_on_all(self, mock_gpio_handler):
        """Test execute_tool_call for turn_device_on (all devices)."""
        result = execute_tool_call("turn_device_on", {"device": "all"})

        assert "All devices turned ON" in result
        mock_gpio_handler.turn_all_on.assert_called_once()

    @patch("waterbot.openai_integration.gpio_handler")
    def test_execute_tool_turn_device_on_unknown(self, mock_gpio_handler):
        """Test execute_tool_call for turn_device_on (unknown device)."""
        mock_gpio_handler.turn_on.return_value = False

        result = execute_tool_call("turn_device_on", {"device": "unknown"})

        assert "Error: Unknown device 'unknown'" in result

    @patch("waterbot.openai_integration.gpio_handler")
    def test_execute_tool_turn_device_off(self, mock_gpio_handler):
        """Test execute_tool_call for turn_device_off."""
        mock_gpio_handler.turn_off.return_value = True

        result = execute_tool_call("turn_device_off", {"device": "pump"})

        assert "Device 'pump' turned OFF" in result
        mock_gpio_handler.turn_off.assert_called_once_with("pump", None)

    @patch("waterbot.openai_integration.gpio_handler")
    def test_execute_tool_turn_device_off_all(self, mock_gpio_handler):
        """Test execute_tool_call for turn_device_off (all devices)."""
        result = execute_tool_call("turn_device_off", {"device": "all"})

        assert "All devices turned OFF" in result
        mock_gpio_handler.turn_all_off.assert_called_once()

    @patch("waterbot.openai_integration.scheduler")
    def test_execute_tool_add_schedule(self, mock_scheduler):
        """Test execute_tool_call for add_schedule."""
        mock_scheduler.add_schedule.return_value = True

        result = execute_tool_call("add_schedule", {"device": "pump", "action": "on", "time": "09:00"})

        assert "Added schedule: pump on at 09:00" in result
        mock_scheduler.add_schedule.assert_called_once_with("pump", "on", "09:00")

    @patch("waterbot.openai_integration.scheduler")
    def test_execute_tool_add_schedule_failure(self, mock_scheduler):
        """Test execute_tool_call for add_schedule (failure)."""
        mock_scheduler.add_schedule.return_value = False

        result = execute_tool_call("add_schedule", {"device": "pump", "action": "on", "time": "09:00"})

        assert "Failed to add schedule for pump" in result

    @patch("waterbot.openai_integration.scheduler")
    def test_execute_tool_remove_schedule(self, mock_scheduler):
        """Test execute_tool_call for remove_schedule."""
        mock_scheduler.remove_schedule.return_value = True

        result = execute_tool_call("remove_schedule", {"device": "pump", "action": "on", "time": "09:00"})

        assert "Removed schedule: pump on at 09:00" in result
        mock_scheduler.remove_schedule.assert_called_once_with("pump", "on", "09:00")

    @patch("waterbot.openai_integration.scheduler")
    def test_execute_tool_remove_schedule_not_found(self, mock_scheduler):
        """Test execute_tool_call for remove_schedule (not found)."""
        mock_scheduler.remove_schedule.return_value = False

        result = execute_tool_call("remove_schedule", {"device": "pump", "action": "on", "time": "09:00"})

        assert "No such schedule found: pump on at 09:00" in result

    @patch("waterbot.openai_integration.scheduler")
    def test_execute_tool_get_schedules_all(self, mock_scheduler):
        """Test execute_tool_call for get_schedules (all devices)."""
        mock_schedules = {
            "pump": {"on": ["09:00"], "off": ["18:00"]},
            "light": {"on": ["08:00"], "off": ["20:00"]},
        }
        mock_scheduler.get_next_runs.return_value = [
            {
                "device": "pump",
                "action": "on",
                "time": "09:00",
                "next_run": "2024-01-01 09:00:00",
            }
        ]

        with patch("waterbot.config.get_schedules", return_value=mock_schedules):
            result = execute_tool_call("get_schedules", {})

        assert "Device Schedules:" in result
        assert "PUMP:" in result
        assert "ON at 09:00" in result
        assert "LIGHT:" in result
        assert "Next scheduled runs:" in result

    @patch("waterbot.openai_integration.scheduler")
    def test_execute_tool_get_schedules_specific_device(self, mock_scheduler):
        """Test execute_tool_call for get_schedules (specific device)."""
        mock_schedules = {"on": ["09:00"], "off": ["18:00"]}
        mock_scheduler.get_next_runs.return_value = []

        with patch("waterbot.config.get_schedules", return_value=mock_schedules):
            result = execute_tool_call("get_schedules", {"device": "pump"})

        assert "Device Schedules:" in result
        assert "PUMP:" in result
        assert "ON at 09:00" in result
        assert "OFF at 18:00" in result

    @patch("waterbot.openai_integration.scheduler")
    def test_execute_tool_get_schedules_no_schedules(self, mock_scheduler):
        """Test execute_tool_call for get_schedules (no schedules)."""
        with patch("waterbot.config.get_schedules", return_value={}):
            result = execute_tool_call("get_schedules", {})

        assert "No schedules configured" in result

    def test_execute_tool_get_current_time(self):
        """Test execute_tool_call for get_current_time."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "America/New_York"

            result = execute_tool_call("get_current_time", {})

            assert "Current Time:" in result

    def test_execute_tool_get_current_time_subprocess_error(self):
        """Test execute_tool_call for get_current_time with subprocess error."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = execute_tool_call("get_current_time", {})

            assert "Current Time:" in result

    def test_execute_tool_get_ip_addresses(self):
        """Test execute_tool_call for get_ip_addresses."""
        with patch("subprocess.run") as mock_run:
            # Mock successful interface listing
            mock_run.side_effect = [
                MagicMock(stdout="eth0\nwlan0\n", returncode=0),
                MagicMock(stdout="2: eth0: inet 192.168.1.100/24", returncode=0),
                MagicMock(stdout="3: wlan0: inet 192.168.1.101/24", returncode=0),
            ]

            result = execute_tool_call("get_ip_addresses", {})

            assert "SSH Access Information:" in result
            assert "ssh pi@192.168.1.100" in result
            assert "ssh pi@192.168.1.101" in result

    def test_execute_tool_get_ip_addresses_no_interfaces(self):
        """Test execute_tool_call for get_ip_addresses with no interfaces."""
        with patch("subprocess.run", side_effect=Exception("Command failed")):
            result = execute_tool_call("get_ip_addresses", {})

            assert "No network interfaces found" in result

    @patch("waterbot.openai_integration.scheduler")
    def test_execute_tool_clear_device_schedule(self, mock_scheduler):
        """Test execute_tool_call for clear_device_schedule."""
        mock_schedules = {"on": ["09:00"], "off": ["18:00"]}
        mock_scheduler.remove_schedule.return_value = True

        with patch("waterbot.config.get_schedules", return_value=mock_schedules):
            result = execute_tool_call("clear_device_schedule", {"device": "pump"})

        assert "Cleared all schedules for 'pump' - removed 2 schedule entries" in result
        assert mock_scheduler.remove_schedule.call_count == 2

    @patch("waterbot.openai_integration.scheduler")
    def test_execute_tool_replace_device_schedule(self, mock_scheduler):
        """Test execute_tool_call for replace_device_schedule."""
        mock_schedules = {"on": ["09:00"], "off": ["18:00"]}
        mock_scheduler.remove_schedule.return_value = True
        mock_scheduler.add_schedule.return_value = True

        schedule_periods = [
            {"start_time": "08:00", "end_time": "12:00"},
            {"start_time": "14:00", "end_time": "18:00"},
        ]

        with patch("waterbot.config.get_schedules", return_value=mock_schedules):
            result = execute_tool_call(
                "replace_device_schedule",
                {"device": "pump", "schedule_periods": schedule_periods},
            )

        assert "Schedule replacement for 'pump' completed" in result
        assert "Removed 2 existing schedules" in result
        assert "Added 4 new schedules" in result
        assert "Period 1: 08:00 to 12:00" in result

    @patch("waterbot.openai_integration.scheduler")
    def test_execute_tool_test_notification(self, mock_scheduler):
        """Test execute_tool_call for test_notification."""
        mock_scheduler_instance = MagicMock()
        mock_scheduler.get_scheduler.return_value = mock_scheduler_instance

        result = execute_tool_call("test_notification", {})

        assert "Test notification sent via scheduler system" in result
        mock_scheduler_instance._send_discord_notification.assert_called_once_with("test_device", "on", True)

    def test_execute_tool_unknown_function(self):
        """Test execute_tool_call with unknown function."""
        result = execute_tool_call("unknown_function", {})

        assert "Unknown function: unknown_function" in result

    def test_execute_tool_exception_handling(self):
        """Test execute_tool_call exception handling."""
        with patch(
            "waterbot.openai_integration.gpio_handler.get_status",
            side_effect=Exception("Test error"),
        ):
            result = execute_tool_call("get_device_status", {})

        assert "Error executing get_device_status: Test error" in result

    @pytest.mark.asyncio
    async def test_process_with_openai_no_client(self):
        """Test process_with_openai when client is not configured."""
        with patch("waterbot.openai_integration.client", None):
            result = await process_with_openai("test message")

            assert "OpenAI is not configured" in result

    @pytest.mark.asyncio
    async def test_process_with_openai_success(self):
        """Test process_with_openai successful processing."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].message.tool_calls = None
        mock_client.chat.completions.create.return_value = mock_response

        with patch("waterbot.openai_integration.client", mock_client):
            result = await process_with_openai("test message")

            assert result == "Test response"
            mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_with_openai_with_tool_calls(self):
        """Test process_with_openai with tool calls."""
        mock_client = MagicMock()

        # First response with tool calls
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "get_device_status"
        mock_tool_call.function.arguments = '{"device": "pump"}'

        mock_first_response = MagicMock()
        mock_first_response.choices[0].message.content = None
        mock_first_response.choices[0].message.tool_calls = [mock_tool_call]

        # Second response after tool execution
        mock_second_response = MagicMock()
        mock_second_response.choices[0].message.content = "Final response"
        mock_second_response.choices[0].message.tool_calls = None

        mock_client.chat.completions.create.side_effect = [
            mock_first_response,
            mock_second_response,
        ]

        with patch("waterbot.openai_integration.client", mock_client), patch(
            "waterbot.openai_integration.execute_tool_call", return_value="Tool result"
        ):

            result = await process_with_openai("test message")

            assert result == "Final response"
            assert mock_client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_process_with_openai_exception(self):
        """Test process_with_openai exception handling."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        with patch("waterbot.openai_integration.client", mock_client):
            result = await process_with_openai("test message")

            assert "Sorry, I encountered an error" in result
            assert "API Error" in result
