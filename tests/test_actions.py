"""Tests for the shared action engine."""

import subprocess
from unittest.mock import MagicMock, patch

from waterbot.actions import ActionEngine
from waterbot.agent.memory import AgentMemory


def test_risky_action_requires_confirmation_and_confirm_executes(tmp_path):
    """Risky actions should be previewed by token and execute only after confirmation."""
    memory = AgentMemory(str(tmp_path / "agent.db"))
    engine = ActionEngine(memory=memory)

    pending = engine.execute_action(
        "all_on",
        {"timeout": 120},
        source="agent",
        channel_id="channel-1",
        require_confirmation=True,
    )

    assert pending.status == "pending_confirmation"
    assert pending.confirmation_token is not None
    assert "confirm" in pending.message

    with patch("waterbot.actions.gpio_handler.turn_all_on") as mock_turn_all_on:
        confirmed = engine.confirm(pending.confirmation_token, channel_id="channel-1")

    assert confirmed.success
    assert confirmed.message == "All devices turned ON for 2 minutes"
    mock_turn_all_on.assert_called_once_with(120)
    assert memory.get_pending_confirmation(pending.confirmation_token, "channel-1") is None


def test_non_risky_status_executes_without_confirmation(tmp_path):
    """Read-only status actions should execute immediately."""
    engine = ActionEngine(memory=AgentMemory(str(tmp_path / "agent.db")))

    with patch("waterbot.actions.gpio_handler.get_status", return_value={"pump": True}):
        result = engine.execute_action("get_device_status", {}, require_confirmation=True)

    assert result.success
    assert "pump: ON" in result.message


def test_policy_decision_history_and_feedback_actions(tmp_path):
    """The action engine should expose decision history and feedback storage."""
    memory = AgentMemory(str(tmp_path / "agent.db"))
    engine = ActionEngine(memory=memory)
    memory.record_policy_decision(
        policy_id="pump-cycle",
        device="pump",
        run_key="2026-07-04T06:00",
        executed=False,
        skipped=True,
        duration_minutes=0,
        message="Skipped because rain was forecast",
        context={"forecast_rain_next_12h_inches": 0.2},
        matched_rules=["forecast rain"],
    )

    history = engine.execute_action(
        "get_policy_decision_history",
        {"device": "pump"},
        require_confirmation=False,
    )
    assert history.success
    assert "pump skipped" in history.message
    assert "forecast rain" in history.message

    feedback = engine.execute_action(
        "record_user_feedback",
        {"device": "pump", "feedback": "soil is still dry", "channel_id": "channel-1"},
        require_confirmation=False,
    )
    assert feedback.success
    assert memory.get_recent_feedback("pump")[0]["feedback"] == "soil is still dry"


def test_preview_cancel_describe_and_default_confirmation(tmp_path):
    """Preview, cancellation, descriptions, and default confirmation policy should work."""
    engine = ActionEngine(memory=AgentMemory(str(tmp_path / "agent.db")))

    preview = engine.preview_action("device_on", {"device": "pump", "duration_minutes": 5})
    assert preview.status == "preview"
    assert preview.message == "Preview: turn pump on for 5 minutes"

    pending = engine.execute_action("all_off", {}, channel_id="channel-1", require_confirmation=None)
    assert pending.status == "pending_confirmation"
    cancelled = engine.cancel(pending.confirmation_token, channel_id="channel-1")
    assert cancelled.status == "cancelled"
    assert engine.confirm(pending.confirmation_token, channel_id="channel-1").status == "not_found"
    assert engine.cancel("missing", channel_id="channel-1").status == "not_found"

    assert engine.describe_action("turn_device_off", {"device": "pump"}) == "turn pump off"
    assert engine.describe_action("all_on", {}) == "turn all devices on"
    assert engine.describe_action("all_off", {}) == "turn all devices off"
    assert engine.describe_action("replace_device_schedule", {"device": "pump"}) == "replace all schedules for pump"
    assert engine.describe_action("clear_device_schedule", {"device": "pump"}) == "clear all schedules for pump"
    assert engine.describe_action("upsert_policy_schedule", {"policy": {"id": "policy-1"}}) == (
        "save flexible policy policy-1"
    )
    assert engine.describe_action("create_every_n_days_cycle", {"device": "pump", "every": 3, "at": "06:00"}) == (
        "create cycle for pump every 3 days at 06:00"
    )
    assert engine.describe_action("policy_remove", {"policy_id": "policy-1"}) == "remove flexible policy policy-1"
    assert engine.describe_action("custom_action", {}) == "custom action"


def test_failed_confirmed_action_is_single_use(tmp_path):
    """A confirmed action token should be consumed even when execution fails."""
    memory = AgentMemory(str(tmp_path / "agent.db"))
    engine = ActionEngine(memory=memory)
    pending = engine.execute_action("all_on", {}, channel_id="channel-1", require_confirmation=True)

    with patch("waterbot.actions.gpio_handler.turn_all_on", side_effect=RuntimeError("relay error")):
        result = engine.confirm(pending.confirmation_token, channel_id="channel-1")

    assert result.status == "error"
    assert "relay error" in result.message
    assert memory.get_pending_confirmation(pending.confirmation_token, "channel-1") is None


def test_device_actions_cover_success_failure_and_aliases(tmp_path):
    """Device action aliases should route to GPIO helpers with correct timeouts."""
    engine = ActionEngine(memory=AgentMemory(str(tmp_path / "agent.db")))

    with patch("waterbot.actions.gpio_handler.turn_on", return_value=True) as mock_turn_on:
        result = engine.execute_action(
            "device_on",
            {"device": "pump", "duration_minutes": 1.5},
            require_confirmation=False,
        )
    assert result.success
    assert "1.5 minutes" in result.message
    mock_turn_on.assert_called_once_with("pump", 90)

    with patch("waterbot.actions.gpio_handler.turn_on", return_value=True) as mock_turn_on:
        result = engine.execute_action("turn_device_on", {"device": "pump", "timeout": 120}, require_confirmation=False)
    assert result.success
    assert "2 minutes" in result.message
    mock_turn_on.assert_called_once_with("pump", 120)

    with patch("waterbot.actions.gpio_handler.turn_on", return_value=False):
        result = engine.execute_action("turn_device_on", {"device": "missing"}, require_confirmation=False)
    assert result.status == "failed"
    assert "Unknown device" in result.message

    with patch("waterbot.actions.gpio_handler.turn_all_on") as mock_turn_all_on:
        result = engine.execute_action("turn_device_on", {"device": "all", "timeout": 60}, require_confirmation=False)
    assert result.success
    assert result.message == "All devices turned ON"
    mock_turn_all_on.assert_called_once_with(60)

    with patch("waterbot.actions.gpio_handler.turn_off", return_value=True) as mock_turn_off:
        result = engine.execute_action(
            "device_off",
            {"device": "pump", "duration_minutes": 2},
            require_confirmation=False,
        )
    assert result.success
    assert "2 minutes" in result.message
    mock_turn_off.assert_called_once_with("pump", 120)

    with patch("waterbot.actions.gpio_handler.turn_off", return_value=False):
        result = engine.execute_action("turn_device_off", {"device": "missing"}, require_confirmation=False)
    assert result.status == "failed"

    with patch("waterbot.actions.gpio_handler.turn_all_off") as mock_turn_all_off:
        result = engine.execute_action("turn_device_off", {"device": "all", "timeout": 60}, require_confirmation=False)
    assert result.success
    assert result.message == "All devices turned OFF"
    mock_turn_all_off.assert_called_once_with(60)


def test_all_schedule_and_status_actions(tmp_path):
    """Status and legacy schedule actions should return user-facing messages."""
    engine = ActionEngine(memory=AgentMemory(str(tmp_path / "agent.db")))

    with patch("waterbot.actions.gpio_handler.turn_all_on") as mock_all_on:
        result = engine.execute_action("all_on", {"timeout": 180}, require_confirmation=False)
    assert result.message == "All devices turned ON for 3 minutes"
    mock_all_on.assert_called_once_with(180)

    with patch("waterbot.actions.gpio_handler.turn_all_off") as mock_all_off:
        result = engine.execute_action("all_off", {}, require_confirmation=False)
    assert result.message == "All devices turned OFF"
    mock_all_off.assert_called_once_with(None)

    with patch("waterbot.actions.gpio_handler.get_status", return_value={}):
        assert (
            engine.execute_action("get_device_status", {}, require_confirmation=False).message
            == "No devices configured"
        )
    with patch("waterbot.actions.gpio_handler.get_status", return_value={"pump": True}):
        assert engine.execute_action("get_device_status", {"device": "pump"}, require_confirmation=False).message == (
            "Device 'pump' is ON"
        )
    with patch("waterbot.actions.gpio_handler.get_status", return_value={"pump": True}):
        result = engine.execute_action("get_device_status", {"device": "missing"}, require_confirmation=False)
    assert result.status == "failed"

    with patch("waterbot.actions.scheduler.add_schedule", return_value=True):
        assert (
            "Added schedule"
            in engine.execute_action(
                "schedule_add",
                {"device": "pump", "action": "on", "time": "06:00"},
                require_confirmation=False,
            ).message
        )
    with patch("waterbot.actions.scheduler.add_schedule", return_value=False):
        assert (
            "Failed to add"
            in engine.execute_action(
                "add_schedule",
                {"device": "pump", "action": "on", "time": "06:00"},
                require_confirmation=False,
            ).message
        )
    with patch("waterbot.actions.scheduler.remove_schedule", return_value=True):
        assert (
            "Removed schedule"
            in engine.execute_action(
                "schedule_remove",
                {"device": "pump", "action": "on", "time": "06:00"},
                require_confirmation=False,
            ).message
        )
    with patch("waterbot.actions.scheduler.remove_schedule", return_value=False):
        assert (
            "No such schedule"
            in engine.execute_action(
                "remove_schedule",
                {"device": "pump", "action": "on", "time": "06:00"},
                require_confirmation=False,
            ).message
        )


def test_schedule_list_replace_and_clear_actions(tmp_path):
    """Schedule listing, replacement, and clearing should use config and scheduler APIs."""
    engine = ActionEngine(memory=AgentMemory(str(tmp_path / "agent.db")))

    with patch("waterbot.config.get_schedules", return_value={}):
        assert (
            engine.execute_action("get_schedules", {}, require_confirmation=False).message == "No schedules configured"
        )
    with patch("waterbot.config.get_schedules", return_value={}):
        assert (
            "for device 'pump'"
            in engine.execute_action(
                "get_schedules",
                {"device": "pump"},
                require_confirmation=False,
            ).message
        )
    with patch("waterbot.config.get_schedules", return_value={"on": ["06:00"], "off": ["06:10"]}):
        result = engine.execute_action("get_schedules", {"device": "pump"}, require_confirmation=False)
    assert "PUMP:" in result.message
    assert "ON at 06:00" in result.message
    with patch("waterbot.config.get_schedules", return_value={"pump": {"on": ["06:00"]}}):
        result = engine.execute_action("get_schedules", {}, require_confirmation=False)
    assert "PUMP:" in result.message

    periods = [{"start_time": "06:00", "end_time": "06:10"}]
    with (
        patch("waterbot.config.get_schedules", return_value={"on": ["05:00"], "off": ["05:10"]}),
        patch("waterbot.actions.scheduler.replace_device_schedules", return_value=True) as mock_replace,
    ):
        result = engine.execute_action(
            "replace_device_schedule",
            {"device": "pump", "schedule_periods": periods},
            require_confirmation=False,
        )
    assert "Schedule replacement" in result.message
    assert "Period 1" in result.message
    mock_replace.assert_called_once_with("pump", {"on": ["06:00"], "off": ["06:10"]})

    with (
        patch("waterbot.config.get_schedules", return_value={}),
        patch("waterbot.actions.scheduler.replace_device_schedules", return_value=False),
    ):
        result = engine.execute_action(
            "replace_device_schedule",
            {"device": "pump", "schedule_periods": periods},
            require_confirmation=False,
        )
    assert result.status == "failed"

    with (
        patch("waterbot.config.get_schedules", return_value={"on": ["06:00"], "off": ["06:10"]}),
        patch("waterbot.actions.scheduler.remove_schedule", side_effect=[True, False]),
    ):
        result = engine.execute_action("clear_device_schedule", {"device": "pump"}, require_confirmation=False)
    assert "removed 1 schedule entries" in result.message


def test_policy_weather_time_ip_and_misc_actions(tmp_path):
    """Policy, weather, node information, and misc actions should be executable."""
    policy = {
        "id": "pump-cycle",
        "device": "pump",
        "enabled": True,
        "recurrence": {"type": "every_n_days", "every": 3, "at": "06:00", "anchor_date": "2026-07-04"},
        "duration": {"base_minutes": 8.0, "min_minutes": 8.0, "max_minutes": 8.0},
        "rules": [],
    }
    weather_provider = MagicMock()
    weather_provider.get_context.return_value = {"temperature_f": 90, "rain_last_24h_inches": 0.1}
    engine = ActionEngine(memory=AgentMemory(str(tmp_path / "agent.db")), weather_provider=weather_provider)

    with patch("waterbot.actions.scheduler.upsert_policy_schedule", return_value=policy):
        assert (
            "Saved flexible schedule"
            in engine.execute_action(
                "upsert_policy_schedule",
                {"policy": policy},
                require_confirmation=False,
            ).message
        )

    with (
        patch("waterbot.policy.DEVICE_TO_PIN", {"pump": 17}),
        patch("waterbot.actions.scheduler.upsert_policy_schedule", return_value=policy),
    ):
        assert (
            "Saved flexible cycle"
            in engine.execute_action(
                "create_every_n_days_cycle",
                {"device": "pump", "every": 3, "at": "06:00", "duration_minutes": 8},
                require_confirmation=False,
            ).message
        )

    with patch("waterbot.actions.scheduler.remove_policy_schedule", return_value=True):
        assert (
            "Removed flexible schedule"
            in engine.execute_action(
                "remove_policy_schedule",
                {"policy_id": "pump-cycle"},
                require_confirmation=False,
            ).message
        )
    with patch("waterbot.actions.scheduler.remove_policy_schedule", return_value=False):
        assert (
            "No such flexible schedule"
            in engine.execute_action(
                "policy_remove",
                {"policy_id": "pump-cycle"},
                require_confirmation=False,
            ).message
        )

    with patch("waterbot.actions.scheduler.get_policy_schedules", return_value=[]):
        assert "No flexible" in engine.execute_action("get_policy_schedules", {}, require_confirmation=False).message
    with patch("waterbot.actions.scheduler.get_policy_schedules", return_value=[policy]):
        assert "pump-cycle" in engine.execute_action("get_policy_schedules", {}, require_confirmation=False).message

    weather = engine.execute_action("get_weather_context", {}, require_confirmation=False)
    assert "temperature_f" in weather.message
    assert weather.data["context"]["temperature_f"] == 90
    weather_provider.get_context.return_value = {}
    assert "No weather" in engine.execute_action("get_weather_context", {}, require_confirmation=False).message

    tz_result = MagicMock(returncode=0, stdout="America/Los_Angeles\n")
    with patch("waterbot.actions.subprocess.run", return_value=tz_result):
        assert (
            "America/Los_Angeles" in engine.execute_action("get_current_time", {}, require_confirmation=False).message
        )
    with patch("waterbot.actions.subprocess.run", side_effect=FileNotFoundError):
        assert "Current Time" in engine.execute_action("get_current_time", {}, require_confirmation=False).message

    interface_result = MagicMock(stdout="lo\neth0\n")
    ip_result = MagicMock(stdout="2: eth0: <UP>\n    inet 192.168.1.50/24 scope global eth0\n")
    with patch("waterbot.actions.subprocess.run", side_effect=[interface_result, ip_result]):
        ip_response = engine.execute_action("get_ip_addresses", {}, require_confirmation=False)
    assert "ssh pi@192.168.1.50" in ip_response.message

    with patch("waterbot.actions.subprocess.run", side_effect=subprocess.CalledProcessError(1, "ls")):
        assert (
            "No network interfaces" in engine.execute_action("get_ip_addresses", {}, require_confirmation=False).message
        )

    scheduler_instance = MagicMock()
    with patch("waterbot.actions.scheduler.get_scheduler", return_value=scheduler_instance):
        assert "Test notification" in engine.execute_action("test_notification", {}, require_confirmation=False).message
    scheduler_instance._send_discord_notification.assert_called_once_with("test_device", "on", True)

    assert engine.execute_action("unknown_action", {}, require_confirmation=False).status == "failed"
    assert engine.execute_action("turn_device_on", {}, require_confirmation=False).status == "error"
