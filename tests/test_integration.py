"""Integration-style tests spanning schedule, GPIO, and action confirmation."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from waterbot.actions import ActionEngine
from waterbot.agent.memory import AgentMemory
from waterbot.gpio.handler import DeviceController
from waterbot.gpio.interface import EmulationGPIO
from waterbot.policy import PolicyScheduler, PolicyScheduleStore, create_every_n_days_policy


class StaticWeatherProvider:
    def __init__(self, context):
        self.context = context

    def get_context(self):
        return self.context


def test_schedule_fire_updates_emulated_gpio():
    """A scheduled job should flip device state through the GPIO controller."""
    gpio = EmulationGPIO()
    with patch("waterbot.gpio.handler.DEVICE_TO_PIN", {"pump": 17}):
        controller = DeviceController(gpio_interface=gpio)
        assert controller.get_status()["pump"] is False

        with patch("waterbot.scheduler.gpio_handler.turn_on", side_effect=controller.turn_on):
            from waterbot.scheduler import DeviceScheduler

            scheduler = DeviceScheduler()
            with patch("waterbot.scheduler.schedule") as mock_schedule:
                mock_schedule.every.return_value.day.at.return_value.do.return_value = MagicMock()
                scheduler._schedule_device_action("pump", "on", "08:00")
                job = mock_schedule.every.return_value.day.at.return_value.do.call_args[0][0]
                job()

        assert controller.get_status()["pump"] is True


def test_policy_skip_and_run_with_weather(tmp_path):
    """Weather-aware policies should skip then run across days."""
    store = PolicyScheduleStore(str(tmp_path / "policies.json"))
    with patch("waterbot.policy.DEVICE_TO_PIN", {"pump": 17}):
        store.upsert_policy(
            create_every_n_days_policy(
                "pump",
                1,
                "06:00",
                8,
                "2024-01-01",
                rules=[{"name": "rain", "when": {"rain_last_24h_inches": {">=": 0.2}}, "then": {"skip": True}}],
            )
        )
        wet = PolicyScheduler(store=store, weather_provider=StaticWeatherProvider({"rain_last_24h_inches": 0.5}))
        dry = PolicyScheduler(store=store, weather_provider=StaticWeatherProvider({"rain_last_24h_inches": 0.0}))

        with patch("waterbot.policy.gpio_handler.turn_on", return_value=True) as mock_on:
            wet_results = wet.run_due(datetime(2024, 1, 1, 6, 0, 30))
            dry_results = dry.run_due(datetime(2024, 1, 2, 6, 0, 30))

    assert wet_results[0].skipped is True
    assert dry_results[0].executed is True
    mock_on.assert_called_once_with("pump", 480)


def test_confirmation_flow_end_to_end(tmp_path):
    """Risky actions require confirm tokens before mutation."""
    memory = AgentMemory(path=str(tmp_path / "agent.db"))
    engine = ActionEngine(memory=memory)

    with patch("waterbot.actions.gpio_handler.turn_all_on") as mock_all_on:
        pending = engine.execute_action("all_on", {}, channel_id="chan", require_confirmation=True)
        assert pending.status == "pending_confirmation"
        assert pending.confirmation_token
        mock_all_on.assert_not_called()

        confirmed = engine.confirm(pending.confirmation_token, channel_id="chan")
        assert confirmed.success is True
        mock_all_on.assert_called_once()
