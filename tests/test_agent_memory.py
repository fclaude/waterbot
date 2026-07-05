"""Tests for SQLite-backed agent memory."""

import sqlite3

from waterbot.agent.memory import AgentMemory


def test_agent_memory_records_context_confirmations_decisions_and_feedback(tmp_path):
    """Test the main persisted agent memory workflows."""
    db_path = tmp_path / "agent.db"
    memory = AgentMemory(str(db_path))

    memory.record_message("channel-1", "user", "status please", author_id="42", author_name="Fran")
    memory.record_message("channel-1", "assistant", "Device Status: pump ON", author_name="WaterBot")

    context = memory.get_context("channel-1")
    assert "status please" in context["summary"]["summary"]
    assert context["recent_messages"][0]["author_name"] == "Fran"
    assert context["recent_messages"][1]["role"] == "assistant"

    token = memory.create_confirmation(
        "all_on",
        {"timeout": 60},
        "turn all devices on",
        channel_id="channel-1",
    )
    pending = memory.get_pending_confirmation(token, "channel-1")
    assert pending is not None
    assert pending["arguments"] == {"timeout": 60}
    assert memory.get_pending_confirmation(token, "other-channel") is None

    memory.resolve_confirmation(token, "cancelled")
    assert memory.get_pending_confirmation(token, "channel-1") is None

    memory.record_action_event(
        action_type="get_device_status",
        arguments={},
        status="success",
        message="Device Status: pump ON",
        source="test",
        channel_id="channel-1",
    )
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute("SELECT action_type, status FROM action_events").fetchone()
    finally:
        connection.close()
    assert row == ("get_device_status", "success")

    memory.record_policy_decision(
        policy_id="pump-cycle",
        device="pump",
        run_key="2026-07-04T06:00",
        executed=True,
        skipped=False,
        duration_minutes=8,
        message="Executed pump-cycle",
        context={"temperature_f": 91},
        matched_rules=["hot day"],
    )
    decisions = memory.get_policy_decision_history("pump")
    assert decisions[0]["device"] == "pump"
    assert decisions[0]["context"] == {"temperature_f": 91}
    assert decisions[0]["matched_rules"] == ["hot day"]

    memory.record_feedback("too dry after the last cycle", channel_id="channel-1", device="pump")
    feedback = memory.get_recent_feedback("pump")
    assert feedback[0]["feedback"] == "too dry after the last cycle"
