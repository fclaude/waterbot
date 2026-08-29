"""Tests for waterbot/openai_integration.py."""

import subprocess
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
            "upsert_policy_schedule",
            "create_every_n_days_cycle",
            "remove_policy_schedule",
            "get_policy_schedules",
            "get_weather_context",
            "get_device_status",
            "turn_device_on",
            "turn_device_off",
            "add_schedule",
            "remove_schedule",
            "get_schedules",
            "get_current_time",
        ]

        for expected_func in expected_functions:
            assert expected_func in function_names
        assert "get_ip_addresses" not in function_names
        assert "test_notification" not in function_names

    @patch("waterbot.actions.gpio_handler")
    def test_execute_tool_get_device_status_all(self, mock_gpio_handler):
        """Test execute_tool_call for get_device_status (all devices)."""
        mock_gpio_handler.get_status.return_value = {"pump": True, "light": False}

        result = execute_tool_call("get_device_status", {})

        assert "Device Status:" in result
        assert "pump: ON" in result
        assert "light: OFF" in result

    @patch("waterbot.actions.gpio_handler")
    def test_execute_tool_get_device_status_specific(self, mock_gpio_handler):
        """Test execute_tool_call for get_device_status (specific device)."""
        mock_gpio_handler.get_status.return_value = {"pump": True, "light": False}

        result = execute_tool_call("get_device_status", {"device": "pump"})

        assert "Device 'pump' is ON" in result

    @patch("waterbot.actions.gpio_handler")
    def test_execute_tool_get_device_status_not_found(self, mock_gpio_handler):
        """Test execute_tool_call for get_device_status (device not found)."""
        mock_gpio_handler.get_status.return_value = {"pump": True}

        result = execute_tool_call("get_device_status", {"device": "unknown"})

        assert "Device 'unknown' not found" in result

    @patch("waterbot.actions.gpio_handler")
    def test_execute_tool_get_device_status_no_devices(self, mock_gpio_handler):
        """Test execute_tool_call for get_device_status (no devices)."""
        mock_gpio_handler.get_status.return_value = {}

        result = execute_tool_call("get_device_status", {})

        assert "No devices configured" in result

    @patch("waterbot.actions.gpio_handler")
    def test_execute_tool_turn_device_on(self, mock_gpio_handler):
        """Test execute_tool_call for turn_device_on."""
        mock_gpio_handler.turn_on.return_value = True

        result = execute_tool_call("turn_device_on", {"device": "pump"})

        assert "Device 'pump' turned ON" in result
        mock_gpio_handler.turn_on.assert_called_once_with("pump", None)

    @patch("waterbot.actions.gpio_handler")
    def test_execute_tool_turn_device_on_with_duration(self, mock_gpio_handler):
        """Test execute_tool_call for turn_device_on with duration."""
        mock_gpio_handler.turn_on.return_value = True

        result = execute_tool_call("turn_device_on", {"device": "pump", "duration_minutes": 30})

        assert "Device 'pump' turned ON for 30 minutes" in result
        mock_gpio_handler.turn_on.assert_called_once_with("pump", 1800)  # 30 * 60

    @patch("waterbot.actions.gpio_handler")
    def test_execute_tool_turn_device_on_all(self, mock_gpio_handler):
        """Test execute_tool_call for turn_device_on (all devices)."""
        result = execute_tool_call("turn_device_on", {"device": "all"})

        assert "All devices turned ON" in result
        mock_gpio_handler.turn_all_on.assert_called_once()

    @patch("waterbot.actions.gpio_handler")
    def test_execute_tool_turn_device_on_unknown(self, mock_gpio_handler):
        """Test execute_tool_call for turn_device_on (unknown device)."""
        mock_gpio_handler.turn_on.return_value = False

        result = execute_tool_call("turn_device_on", {"device": "unknown"})

        assert "Error: Unknown device 'unknown'" in result

    @patch("waterbot.actions.gpio_handler")
    def test_execute_tool_turn_device_off(self, mock_gpio_handler):
        """Test execute_tool_call for turn_device_off."""
        mock_gpio_handler.turn_off.return_value = True

        result = execute_tool_call("turn_device_off", {"device": "pump"})

        assert "Device 'pump' turned OFF" in result
        mock_gpio_handler.turn_off.assert_called_once_with("pump", None)

    @patch("waterbot.actions.gpio_handler")
    def test_execute_tool_turn_device_off_all(self, mock_gpio_handler):
        """Test execute_tool_call for turn_device_off (all devices)."""
        result = execute_tool_call("turn_device_off", {"device": "all"})

        assert "All devices turned OFF" in result
        mock_gpio_handler.turn_all_off.assert_called_once()

    @patch("waterbot.actions.scheduler")
    def test_execute_tool_add_schedule(self, mock_scheduler):
        """Test execute_tool_call for add_schedule."""
        mock_scheduler.add_schedule.return_value = True

        result = execute_tool_call("add_schedule", {"device": "pump", "action": "on", "time": "09:00"})

        assert "Added schedule: pump on at 09:00" in result
        mock_scheduler.add_schedule.assert_called_once_with("pump", "on", "09:00")

    @patch("waterbot.actions.scheduler")
    def test_execute_tool_add_schedule_failure(self, mock_scheduler):
        """Test execute_tool_call for add_schedule (failure)."""
        mock_scheduler.add_schedule.return_value = False

        result = execute_tool_call("add_schedule", {"device": "pump", "action": "on", "time": "09:00"})

        assert "Failed to add schedule for pump" in result

    @patch("waterbot.actions.scheduler")
    def test_execute_tool_remove_schedule(self, mock_scheduler):
        """Test execute_tool_call for remove_schedule."""
        mock_scheduler.remove_schedule.return_value = True

        result = execute_tool_call("remove_schedule", {"device": "pump", "action": "on", "time": "09:00"})

        assert "Removed schedule: pump on at 09:00" in result
        mock_scheduler.remove_schedule.assert_called_once_with("pump", "on", "09:00")

    @patch("waterbot.actions.scheduler")
    def test_execute_tool_remove_schedule_not_found(self, mock_scheduler):
        """Test execute_tool_call for remove_schedule (not found)."""
        mock_scheduler.remove_schedule.return_value = False

        result = execute_tool_call("remove_schedule", {"device": "pump", "action": "on", "time": "09:00"})

        assert "No such schedule found: pump on at 09:00" in result

    @patch("waterbot.actions.scheduler")
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

    @patch("waterbot.actions.scheduler")
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

    @patch("waterbot.actions.scheduler")
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

    def test_execute_tool_get_ip_addresses_is_disallowed(self):
        """Agent tool path must not expose IP lookup."""
        result = execute_tool_call("get_ip_addresses", {})
        assert "not available" in result

    def test_execute_tool_get_ip_addresses_no_interfaces_is_disallowed(self):
        """Agent tool path must not expose IP lookup even when no interfaces exist."""
        result = execute_tool_call("get_ip_addresses", {})
        assert "not available" in result

    @patch("waterbot.actions.scheduler")
    def test_execute_tool_clear_device_schedule(self, mock_scheduler):
        """Test execute_tool_call for clear_device_schedule."""
        mock_schedules = {"on": ["09:00"], "off": ["18:00"]}
        mock_scheduler.remove_schedule.return_value = True

        with patch("waterbot.config.get_schedules", return_value=mock_schedules):
            result = execute_tool_call("clear_device_schedule", {"device": "pump"})

        assert "Cleared all schedules for 'pump' - removed 2 schedule entries" in result
        assert mock_scheduler.remove_schedule.call_count == 2

    @patch("waterbot.actions.scheduler")
    def test_execute_tool_replace_device_schedule(self, mock_scheduler):
        """Test execute_tool_call for replace_device_schedule."""
        mock_schedules = {"on": ["09:00"], "off": ["18:00"]}
        mock_scheduler.replace_device_schedules.return_value = True

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
        mock_scheduler.replace_device_schedules.assert_called_once_with(
            "pump",
            {"on": ["08:00", "14:00"], "off": ["12:00", "18:00"]},
        )

    def test_execute_tool_test_notification_is_disallowed(self):
        """Agent tool path must not send test notifications."""
        result = execute_tool_call("test_notification", {})
        assert "not available" in result

    @patch("waterbot.actions.scheduler")
    def test_execute_tool_create_every_n_days_cycle(self, mock_scheduler):
        """Test execute_tool_call for create_every_n_days_cycle."""
        mock_scheduler.upsert_policy_schedule.return_value = {
            "id": "pump-every-3-days-0600",
            "device": "pump",
            "enabled": True,
            "recurrence": {
                "type": "every_n_days",
                "every": 3,
                "at": "06:00",
                "anchor_date": "2024-01-01",
            },
            "duration": {"base_minutes": 8.0, "min_minutes": 8.0, "max_minutes": 8.0},
            "rules": [],
        }

        result = execute_tool_call(
            "create_every_n_days_cycle",
            {
                "device": "pump",
                "every": 3,
                "at": "06:00",
                "duration_minutes": 8,
                "anchor_date": "2024-01-01",
            },
        )

        assert "Saved flexible cycle" in result
        mock_scheduler.upsert_policy_schedule.assert_called_once()

    @patch("waterbot.actions.scheduler")
    def test_execute_tool_get_policy_schedules(self, mock_scheduler):
        """Test execute_tool_call for get_policy_schedules."""
        mock_scheduler.get_policy_schedules.return_value = [
            {
                "id": "pump-every-3-days-0600",
                "device": "pump",
                "enabled": True,
                "recurrence": {
                    "type": "every_n_days",
                    "every": 3,
                    "at": "06:00",
                    "anchor_date": "2024-01-01",
                },
                "duration": {"base_minutes": 8.0, "min_minutes": 8.0, "max_minutes": 8.0},
                "rules": [],
            }
        ]

        result = execute_tool_call("get_policy_schedules", {})

        assert "Flexible Policy Schedules" in result
        assert "pump-every-3-days-0600" in result

    @patch("waterbot.openai_integration.get_action_engine")
    def test_execute_tool_passes_confirmation_context(self, mock_get_action_engine):
        """Risky direct tools should pass execution context to ActionEngine."""
        engine = MagicMock()
        mock_get_action_engine.return_value = engine
        engine.execute_action.return_value.message = "Confirmation required"
        arguments = {"device": "pump", "schedule_periods": []}

        result = execute_tool_call(
            "replace_device_schedule",
            arguments,
            channel_id="channel-123",
            source="agent",
            require_confirmation=True,
        )

        assert result == "Confirmation required"
        engine.execute_action.assert_called_once_with(
            "replace_device_schedule",
            arguments,
            source="agent",
            channel_id="channel-123",
            require_confirmation=True,
        )

    def test_execute_tool_unknown_function(self):
        """Test execute_tool_call with unknown function."""
        result = execute_tool_call("unknown_function", {})

        assert "not available" in result

    def test_execute_tool_exception_handling(self):
        """Test execute_tool_call exception handling."""
        with patch(
            "waterbot.actions.gpio_handler.get_status",
            side_effect=Exception("Test error"),
        ):
            result = execute_tool_call("get_device_status", {})

        assert "Error executing get_device_status: Test error" in result

    @pytest.mark.asyncio
    async def test_process_with_openai_no_client(self):
        """Test process_with_openai when client is not configured."""
        with (
            patch("waterbot.openai_integration.client", None),
            patch("waterbot.openai_integration.get_openai_client", return_value=None),
        ):
            result = await process_with_openai("test message")

            assert "not configured" in result.lower()
            assert "OPENAI_API_KEY" in result

    @pytest.mark.asyncio
    async def test_process_with_openai_success(self, tmp_path):
        """Test process_with_openai successful processing."""
        from waterbot.agent.memory import AgentMemory
        from waterbot.agent.runtime import AgentRuntime
        from waterbot.services import set_agent_runtime

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].message.tool_calls = None
        mock_client.chat.completions.create.return_value = mock_response

        memory = AgentMemory(str(tmp_path / "agent.db"))
        set_agent_runtime(AgentRuntime(client=mock_client, model="test", memory=memory))

        with patch("waterbot.openai_integration.client", mock_client):
            result = await process_with_openai("test message")

            assert result == "Test response"
            mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_with_openai_with_tool_calls(self, tmp_path):
        """Test process_with_openai with tool calls."""
        from waterbot.actions import ActionResult
        from waterbot.agent.memory import AgentMemory
        from waterbot.agent.runtime import AgentRuntime
        from waterbot.services import set_agent_runtime

        mock_client = MagicMock()

        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "get_device_status"
        mock_tool_call.function.arguments = '{"device": "pump"}'

        mock_first_response = MagicMock()
        mock_first_response.choices[0].message.content = None
        mock_first_response.choices[0].message.tool_calls = [mock_tool_call]

        mock_second_response = MagicMock()
        mock_second_response.choices[0].message.content = "Final response"
        mock_second_response.choices[0].message.tool_calls = None

        mock_client.chat.completions.create.side_effect = [
            mock_first_response,
            mock_second_response,
        ]

        memory = AgentMemory(str(tmp_path / "agent.db"))
        action_engine = MagicMock()
        action_engine.execute_action.return_value = ActionResult("success", "Tool result")
        set_agent_runtime(
            AgentRuntime(
                client=mock_client,
                model="test",
                memory=memory,
                action_engine=action_engine,
            )
        )

        with patch("waterbot.openai_integration.client", mock_client):
            result = await process_with_openai("test message")

            assert result == "Final response"
            assert mock_client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_process_with_openai_exception(self, tmp_path):
        """Test process_with_openai exception handling."""
        from waterbot.agent.memory import AgentMemory
        from waterbot.agent.runtime import AgentRuntime
        from waterbot.services import set_agent_runtime

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        set_agent_runtime(
            AgentRuntime(
                client=mock_client,
                model="test",
                memory=AgentMemory(str(tmp_path / "agent.db")),
            )
        )

        with patch("waterbot.openai_integration.client", mock_client):
            result = await process_with_openai("test message")

            assert "Sorry, I encountered an error" in result
            assert "API Error" in result
