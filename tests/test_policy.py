"""Tests for flexible policy schedules."""

from datetime import datetime
from unittest.mock import patch

from waterbot.policy import (
    PolicyScheduleStore,
    PolicyScheduler,
    create_every_n_days_policy,
    evaluate_policy,
    get_due_run_key,
    get_next_run,
)


class StaticWeatherProvider:
    """Static weather provider for policy tests."""

    def __init__(self, context):
        """Initialize provider."""
        self.context = context

    def get_context(self):
        """Return static context."""
        return self.context


def test_policy_store_upsert_list_remove(tmp_path):
    """Test policy persistence operations."""
    path = str(tmp_path / "policies.json")
    store = PolicyScheduleStore(path)

    with patch("waterbot.policy.DEVICE_TO_PIN", {"pump": 17}):
        saved = store.upsert_policy(create_every_n_days_policy("pump", 3, "06:00", 8, "2024-01-01"))
        policies = store.list_policies()
        removed = store.remove_policy(saved["id"])

    assert len(policies) == 1
    assert policies[0]["device"] == "pump"
    assert removed is True
    assert store.list_policies() == []


def test_every_n_days_due_key():
    """Test every-N-days recurrence matching."""
    with patch("waterbot.policy.DEVICE_TO_PIN", {"pump": 17}):
        policy = PolicyScheduleStore()._normalize_policy(
            create_every_n_days_policy("pump", 3, "06:00", 8, "2024-01-01")
        )

    assert get_due_run_key(policy, datetime(2024, 1, 4, 6, 0, 30)) == "2024-01-04T06:00"
    assert get_due_run_key(policy, datetime(2024, 1, 5, 6, 0, 30)) is None


def test_policy_rules_can_skip_for_rain():
    """Test rain rules can skip a policy run."""
    policy = {
        "id": "pump-rain-skip",
        "device": "pump",
        "recurrence": {"type": "daily", "at": "06:00"},
        "duration": {"base_minutes": 8, "min_minutes": 2, "max_minutes": 12},
        "rules": [
            {
                "name": "rain skip",
                "when": {"rain_last_24h_inches": {">=": 0.25}},
                "then": {"skip": True},
            }
        ],
    }

    plan = evaluate_policy(policy, {"rain_last_24h_inches": 0.3}, "2024-01-01T06:00")

    assert plan.should_run is False
    assert plan.reason == "rain skip"


def test_policy_rules_adjust_duration():
    """Test weather rules can shorten and lengthen duration within bounds."""
    policy = {
        "id": "pump-weather-adjust",
        "device": "pump",
        "recurrence": {"type": "daily", "at": "06:00"},
        "duration": {"base_minutes": 8, "min_minutes": 2, "max_minutes": 12},
        "rules": [
            {
                "name": "forecast rain",
                "when": {"forecast_rain_next_12h_inches": {">=": 0.1}},
                "then": {"duration_multiplier": 0.5},
            },
            {
                "name": "hot day",
                "when": {"temperature_f": {">=": 90}},
                "then": {"duration_multiplier": 1.25},
            },
        ],
    }

    plan = evaluate_policy(
        policy,
        {"forecast_rain_next_12h_inches": 0.2, "temperature_f": 95},
        "2024-01-01T06:00",
    )

    assert plan.should_run is True
    assert plan.duration_minutes == 5.0
    assert plan.matched_rules == ["forecast rain", "hot day"]


def test_policy_scheduler_executes_due_policy_once(tmp_path):
    """Test due policies execute once per run key."""
    path = str(tmp_path / "policies.json")
    store = PolicyScheduleStore(path)

    with patch("waterbot.policy.DEVICE_TO_PIN", {"pump": 17}):
        store.upsert_policy(create_every_n_days_policy("pump", 1, "06:00", 8, "2024-01-01"))

        scheduler = PolicyScheduler(store=store, weather_provider=StaticWeatherProvider({}))
        with patch("waterbot.policy.gpio_handler.turn_on", return_value=True) as mock_turn_on:
            first_results = scheduler.run_due(datetime(2024, 1, 1, 6, 0, 30))
            second_results = scheduler.run_due(datetime(2024, 1, 1, 6, 0, 45))

    assert len(first_results) == 1
    assert first_results[0].executed is True
    assert second_results == []
    mock_turn_on.assert_called_once_with("pump", 480)


def test_get_next_run_for_every_n_days():
    """Test next-run calculation for every-N-days policies."""
    with patch("waterbot.policy.DEVICE_TO_PIN", {"pump": 17}):
        policy = PolicyScheduleStore()._normalize_policy(
            create_every_n_days_policy("pump", 3, "06:00", 8, "2024-01-01")
        )

    next_run = get_next_run(policy, datetime(2024, 1, 2, 7, 0, 0))

    assert next_run == datetime(2024, 1, 4, 6, 0)
