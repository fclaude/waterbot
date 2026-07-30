"""Additional coverage for flexible policy schedules."""

from datetime import date, datetime
from unittest.mock import patch

import pytest

from waterbot.policy import (
    PolicyScheduler,
    PolicyScheduleStore,
    PolicyValidationError,
    create_every_n_days_policy,
    evaluate_policy,
    get_due_run_key,
    get_next_policy_runs,
    get_next_run,
    list_policies,
    policy_summary,
    remove_policy,
    upsert_policy,
)


class StaticWeatherProvider:
    def __init__(self, context):
        self.context = context

    def get_context(self):
        return self.context


def test_store_get_policy_and_corrupt_file(tmp_path):
    path = tmp_path / "policies.json"
    path.write_text("{not-json", encoding="utf-8")
    store = PolicyScheduleStore(str(path))
    assert store.list_policies() == []

    path.write_text('{"policies": [{"id": "x"}]}', encoding="utf-8")
    with patch("waterbot.policy.DEVICE_TO_PIN", {"pump": 17}):
        with pytest.raises(PolicyValidationError):
            store.list_policies()


def test_store_list_format_variants(tmp_path):
    path = tmp_path / "policies.json"
    store = PolicyScheduleStore(str(path))

    with patch("waterbot.policy.DEVICE_TO_PIN", {"pump": 17}):
        policy = create_every_n_days_policy("pump", 2, "07:00", 5, "2024-01-01")
        store.upsert_policy(policy)
        assert store.get_policy(policy["id"])["device"] == "pump"
        assert store.get_policy("missing") is None
        assert store.remove_policy("missing") is False

        # Preserve last_run_key on upsert.
        store.mark_run(policy["id"], "2024-01-01T07:00")
        updated = store.upsert_policy({**policy, "duration": {"base_minutes": 6}})
        assert updated["last_run_key"] == "2024-01-01T07:00"
        assert updated["duration"]["base_minutes"] == 6.0


def test_weekly_and_seasonal_windows():
    with patch("waterbot.policy.DEVICE_TO_PIN", {"pump": 17}):
        store = PolicyScheduleStore("/tmp/unused-policies.json")
        policy = store._normalize_policy(
            {
                "id": "pump-weekly",
                "device": "pump",
                "recurrence": {
                    "type": "weekly",
                    "days": ["mon", "Wednesday"],
                    "at": "06:00",
                    "active_between": {"start": "04-01", "end": "10-31"},
                },
                "duration": {"base_minutes": 5},
            }
        )

    # 2024-04-01 is a Monday inside the window.
    assert get_due_run_key(policy, datetime(2024, 4, 1, 6, 0, 30)) == "2024-04-01T06:00"
    # Tuesday should not match weekly days.
    assert get_due_run_key(policy, datetime(2024, 4, 2, 6, 0, 30)) is None
    # January is outside the active window.
    assert get_due_run_key(policy, datetime(2024, 1, 1, 6, 0, 30)) is None

    next_run = get_next_run(policy, datetime(2024, 3, 31, 12, 0, 0))
    assert next_run == datetime(2024, 4, 1, 6, 0)


def test_daily_wraparound_active_window():
    policy = {
        "id": "winter",
        "device": "pump",
        "recurrence": {
            "type": "daily",
            "at": "08:00",
            "active_between": {"start": "11-01", "end": "02-28"},
        },
        "duration": {"base_minutes": 4, "min_minutes": 1, "max_minutes": 10},
        "rules": [],
    }
    assert get_due_run_key(policy, datetime(2024, 12, 15, 8, 0, 30)) == "2024-12-15T08:00"
    assert get_due_run_key(policy, datetime(2024, 6, 15, 8, 0, 30)) is None


def test_evaluate_duration_delta_and_absolute():
    policy = {
        "id": "pump-delta",
        "device": "pump",
        "duration": {"base_minutes": 8, "min_minutes": 2, "max_minutes": 20},
        "rules": [
            {
                "name": "set absolute",
                "when": {"temperature_f": {">=": 100}},
                "then": {"duration_minutes": 12},
            },
            {
                "name": "add minutes",
                "when": {"temperature_f": {"==": 100}},
                "then": {"duration_delta_minutes": 3},
            },
        ],
    }
    plan = evaluate_policy(policy, {"temperature_f": 100}, "run")
    assert plan.should_run is True
    assert plan.duration_minutes == 15.0
    assert plan.matched_rules == ["set absolute", "add minutes"]


def test_evaluate_equality_condition_without_operator():
    policy = {
        "id": "eq",
        "device": "pump",
        "duration": {"base_minutes": 5, "min_minutes": 1, "max_minutes": 10},
        "rules": [{"name": "exact", "when": {"temperature_f": 90}, "then": {"skip": True}}],
    }
    assert evaluate_policy(policy, {"temperature_f": 90}, "run").should_run is False
    assert evaluate_policy(policy, {"temperature_f": 89}, "run").should_run is True


def test_policy_scheduler_skips_disabled_and_failed_gpio(tmp_path):
    path = str(tmp_path / "policies.json")
    store = PolicyScheduleStore(path)
    with patch("waterbot.policy.DEVICE_TO_PIN", {"pump": 17}):
        enabled = create_every_n_days_policy("pump", 1, "06:00", 8, "2024-01-01")
        disabled = create_every_n_days_policy("pump", 1, "06:00", 8, "2024-01-01", policy_id="disabled")
        disabled["enabled"] = False
        store.upsert_policy(enabled)
        store.upsert_policy(disabled)

        scheduler = PolicyScheduler(store=store, weather_provider=StaticWeatherProvider({}))
        with patch("waterbot.policy.gpio_handler.turn_on", return_value=False):
            results = scheduler.run_due(datetime(2024, 1, 1, 6, 0, 30))

    assert len(results) == 1
    assert results[0].executed is False
    assert results[0].skipped is False


def test_policy_scheduler_records_skip(tmp_path):
    path = str(tmp_path / "policies.json")
    store = PolicyScheduleStore(path)
    with patch("waterbot.policy.DEVICE_TO_PIN", {"pump": 17}):
        policy = create_every_n_days_policy(
            "pump",
            1,
            "06:00",
            8,
            "2024-01-01",
            rules=[{"name": "rain", "when": {"rain_last_24h_inches": {">=": 0.1}}, "then": {"skip": True}}],
        )
        store.upsert_policy(policy)
        scheduler = PolicyScheduler(
            store=store,
            weather_provider=StaticWeatherProvider({"rain_last_24h_inches": 0.5}),
        )
        results = scheduler.run_due(datetime(2024, 1, 1, 6, 0, 30))

    assert len(results) == 1
    assert results[0].skipped is True


def test_validation_errors():
    store = PolicyScheduleStore("/tmp/unused.json")
    with patch("waterbot.policy.DEVICE_TO_PIN", {"pump": 17}):
        with pytest.raises(PolicyValidationError):
            store._normalize_policy({"device": "pump", "recurrence": "bad", "duration": {"base_minutes": 1}})
        with pytest.raises(PolicyValidationError):
            store._normalize_policy(
                {
                    "device": "pump",
                    "recurrence": {"type": "hourly", "at": "06:00"},
                    "duration": {"base_minutes": 1},
                }
            )
        with pytest.raises(PolicyValidationError):
            store._normalize_policy(
                {
                    "device": "pump",
                    "recurrence": {"type": "every_n_days", "every": 0, "at": "06:00"},
                    "duration": {"base_minutes": 1},
                }
            )
        with pytest.raises(PolicyValidationError):
            store._normalize_policy(
                {
                    "device": "pump",
                    "recurrence": {"type": "weekly", "days": [], "at": "06:00"},
                    "duration": {"base_minutes": 1},
                }
            )
        with pytest.raises(PolicyValidationError):
            store._normalize_policy(
                {
                    "device": "pump",
                    "recurrence": {"type": "daily", "at": "06:00"},
                    "duration": {"base_minutes": 5, "min_minutes": 10, "max_minutes": 2},
                }
            )
        with pytest.raises(PolicyValidationError):
            store._normalize_policy(
                {
                    "device": "pump",
                    "recurrence": {"type": "daily", "at": "06:00"},
                    "duration": {"base_minutes": 5},
                    "rules": [{"when": {"temperature_f": {"~~": 1}}, "then": {}}],
                }
            )


def test_policy_summary_and_module_helpers(tmp_path, monkeypatch):
    path = str(tmp_path / "policies.json")
    monkeypatch.setattr("waterbot.policy.POLICY_SCHEDULE_CONFIG_FILE", path)
    with patch("waterbot.policy.DEVICE_TO_PIN", {"pump": 17}):
        policy = upsert_policy(create_every_n_days_policy("pump", 3, "06:00", 8, "2024-01-01"))
        summary = policy_summary(policy)
        assert "pump" in summary
        assert "every 3 days" in summary
        assert list_policies()[0]["id"] == policy["id"]
        runs = get_next_policy_runs(datetime(2024, 1, 2, 7, 0, 0))
        assert runs and runs[0]["id"] == policy["id"]
        assert remove_policy(policy["id"]) is True


def test_auto_generated_policy_id():
    with patch("waterbot.policy.DEVICE_TO_PIN", {"pump": 17}):
        store = PolicyScheduleStore("/tmp/unused.json")
        policy = store._normalize_policy(
            {
                "device": "pump",
                "recurrence": {"type": "daily", "at": "09:15"},
                "duration": {"base_minutes": 3},
            }
        )
    assert policy["id"].startswith("policy-")


def test_anchor_before_today_not_due():
    with patch("waterbot.policy.DEVICE_TO_PIN", {"pump": 17}):
        store = PolicyScheduleStore("/tmp/unused.json")
        policy = store._normalize_policy(create_every_n_days_policy("pump", 3, "06:00", 8, "2024-01-10"))
    # Before anchor date should not match recurrence.
    assert get_due_run_key(policy, datetime(2024, 1, 4, 6, 0, 30)) is None
    assert date.fromisoformat("2024-01-10") == date(2024, 1, 10)
