"""Tests for SQLite-backed agent memory."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

from waterbot.agent.memory import AgentMemory


def test_agent_memory_records_context_confirmations_decisions_and_feedback(tmp_path):
    """Test the main persisted agent memory workflows."""
    db_path = tmp_path / "agent.db"
    memory = AgentMemory(str(db_path))

    memory.record_message("channel-1", "user", "status please", author_id="42", author_name="Fran")
    memory.record_message("channel-1", "assistant", "Device Status: pump ON", author_name="WaterBot")

    context = memory.get_context("channel-1")
    assert context["recent_messages"][0]["author_name"] == "Fran"
    assert context["recent_messages"][1]["role"] == "assistant"
    conversation = memory.get_conversation_messages("channel-1")
    assert conversation[0] == {"role": "user", "content": "status please"}
    assert conversation[1] == {"role": "assistant", "content": "Device Status: pump ON"}

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
    assert any(item["token"] == token for item in memory.get_pending_confirmations("channel-1"))

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
    events = memory.get_recent_action_events("channel-1")
    assert events[0]["action_type"] == "get_device_status"
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


def test_agent_memory_folds_old_messages_into_summary(tmp_path, monkeypatch):
    """Older turns should collapse into the long-term summary."""
    monkeypatch.setattr("waterbot.agent.memory.AGENT_CONTEXT_MESSAGE_LIMIT", 2)
    monkeypatch.setattr("waterbot.agent.memory.AGENT_SUMMARY_MAX_CHARS", 2000)
    memory = AgentMemory(str(tmp_path / "agent.db"))

    memory.record_message("ch", "user", "first", author_name="Fran")
    memory.record_message("ch", "assistant", "ack 1", author_name="WaterBot")
    memory.record_message("ch", "user", "second", author_name="Fran")
    memory.record_message("ch", "assistant", "ack 2", author_name="WaterBot")

    context = memory.get_context("ch", limit=2)
    assert len(context["recent_messages"]) == 2
    assert "first" in context["summary"]["summary"]
    assert context["recent_messages"][0]["content"] == "second"


def test_agent_memory_is_thread_safe(tmp_path):
    """Concurrent writers should not corrupt the SQLite store."""
    memory = AgentMemory(str(tmp_path / "agent.db"))

    def write(index: int) -> None:
        memory.record_message("threaded", "user", f"message-{index}", author_name=f"u{index}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(40)))

    context = memory.get_context("threaded", limit=24)
    assert len(context["recent_messages"]) == 24
    assert context["recent_messages"][-1]["content"] == "message-39"
    assert "message-0" in context["summary"]["summary"]
