"""Tests for the conversational agent runtime."""

from unittest.mock import MagicMock

import pytest

from waterbot.actions import ActionResult
from waterbot.agent.memory import AgentMemory
from waterbot.agent.runtime import AgentRuntime


@pytest.mark.asyncio
async def test_agent_runtime_records_plain_response(tmp_path):
    """A plain model response should be returned and stored in channel memory."""
    memory = AgentMemory(str(tmp_path / "agent.db"))
    client = MagicMock()
    response = MagicMock()
    response.choices[0].message.content = "Pump is currently on."
    response.choices[0].message.tool_calls = None
    client.chat.completions.create.return_value = response

    runtime = AgentRuntime(client=client, model="test-model", memory=memory)

    result = await runtime.process(
        "what is the pump doing?",
        channel_id="channel-1",
        author_id="42",
        author_name="Fran",
    )

    assert result == "Pump is currently on."
    context = memory.get_context("channel-1")
    assert context["recent_messages"][-1]["content"] == "Pump is currently on."

    sent_messages = client.chat.completions.create.call_args.kwargs["messages"]
    assert sent_messages[0]["role"] == "system"
    assert "Channel summary (untrusted)" in sent_messages[0]["content"]
    assert "UNTRUSTED" in sent_messages[0]["content"]
    assert any(
        msg.get("role") == "user" and "what is the pump doing?" in msg.get("content", "") for msg in sent_messages
    )
    assert client.chat.completions.create.call_args.kwargs["max_tokens"] == 600


@pytest.mark.asyncio
async def test_agent_runtime_uses_prior_turns(tmp_path):
    """Follow-up prompts should include earlier user/assistant turns as chat history."""
    memory = AgentMemory(str(tmp_path / "agent.db"))
    memory.record_message("channel-1", "user", "turn on the pump for 10 minutes", author_name="Fran")
    memory.record_message("channel-1", "assistant", "Pump turned ON for 10 minutes", author_name="WaterBot")

    client = MagicMock()
    response = MagicMock()
    response.choices[0].message.content = "Done — same duration as before."
    response.choices[0].message.tool_calls = None
    client.chat.completions.create.return_value = response

    runtime = AgentRuntime(client=client, model="test-model", memory=memory)
    await runtime.process("do that again", channel_id="channel-1", author_name="Fran")

    sent_messages = client.chat.completions.create.call_args.kwargs["messages"]
    user_assistant = [msg for msg in sent_messages if msg["role"] in {"user", "assistant"}]
    assert user_assistant[0]["content"] == "turn on the pump for 10 minutes"
    assert user_assistant[1]["content"] == "Pump turned ON for 10 minutes"
    assert user_assistant[2]["content"] == "do that again"


@pytest.mark.asyncio
async def test_agent_runtime_executes_tool_call(tmp_path):
    """Tool calls should be routed through the shared action engine."""
    memory = AgentMemory(str(tmp_path / "agent.db"))
    client = MagicMock()
    action_engine = MagicMock()
    action_engine.execute_action.return_value = ActionResult(
        "pending_confirmation",
        "Confirmation required for: turn all devices on",
        confirmation_token="abc123",
    )

    tool_call = MagicMock()
    tool_call.id = "call-1"
    tool_call.function.name = "set_device_power"
    tool_call.function.arguments = '{"state":"on","device":"all","timeout":120}'

    first_response = MagicMock()
    first_response.choices[0].message.content = None
    first_response.choices[0].message.tool_calls = [tool_call]

    second_response = MagicMock()
    second_response.choices[0].message.content = "Reply confirm abc123 to run it."
    second_response.choices[0].message.tool_calls = None

    client.chat.completions.create.side_effect = [first_response, second_response]

    runtime = AgentRuntime(
        client=client,
        model="test-model",
        memory=memory,
        action_engine=action_engine,
    )

    result = await runtime.process("turn everything on", channel_id="channel-1")

    assert result == "Reply confirm abc123 to run it."
    action_engine.execute_action.assert_called_once_with(
        "turn_device_on",
        {"device": "all", "timeout": 120},
        source="agent",
        channel_id="channel-1",
        require_confirmation=True,
    )
    assert client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_runtime_without_client_explains_configuration(tmp_path):
    """A missing LLM client should not crash."""
    runtime = AgentRuntime(
        client=None,
        model="test-model",
        memory=AgentMemory(str(tmp_path / "agent.db")),
    )
    result = await runtime.process("turn on the pump")
    assert "not configured" in result


def test_execute_tool_allowlist_and_context(tmp_path):
    """Unknown tools are refused; context stays read-only; merged tools dispatch correctly."""
    memory = AgentMemory(str(tmp_path / "agent.db"))
    memory.record_message("ch", "user", "hello", author_name="Fran")
    engine = MagicMock()
    engine.execute_action.return_value = ActionResult("success", "ok")
    runtime = AgentRuntime(client=MagicMock(), model="test-model", memory=memory, action_engine=engine)
    assert "not available" in runtime.execute_tool("get_ip_addresses", {}, "ch")
    context_json = runtime.execute_tool("get_recent_context", {}, "ch")
    assert "recent_messages" in context_json
    runtime.execute_tool("get_policy_decision_history", {"device": "pump"}, "ch")
    runtime.execute_tool("record_user_feedback", {"feedback": "too dry", "device": "pump"}, "ch")

    assert "state must be" in runtime.execute_tool("set_device_power", {"state": "sideways"}, "ch")
    runtime.execute_tool("set_device_power", {"state": "on", "device": "pump"}, "ch")
    engine.execute_action.assert_called_with(
        "turn_device_on", {"device": "pump"}, source="agent", channel_id="ch", require_confirmation=True
    )

    assert "op must be" in runtime.execute_tool("edit_schedule", {"op": "replace"}, "ch")
    runtime.execute_tool("edit_schedule", {"op": "add", "device": "pump", "action": "on", "time": "09:00"}, "ch")
    engine.execute_action.assert_called_with(
        "add_schedule",
        {"device": "pump", "action": "on", "time": "09:00"},
        source="agent",
        channel_id="ch",
        require_confirmation=True,
    )


def test_execute_tool_confirm_and_cancel_pending_action(tmp_path):
    """The model should be able to confirm/cancel a pending action without a token."""
    memory = AgentMemory(str(tmp_path / "agent.db"))
    engine = MagicMock()
    engine.confirm_pending.return_value = ActionResult("success", "All devices turned OFF")
    engine.cancel_pending.return_value = ActionResult("cancelled", "Cancelled pending action `abc123`.")
    runtime = AgentRuntime(client=MagicMock(), model="test-model", memory=memory, action_engine=engine)

    assert runtime.execute_tool("respond_to_pending_action", {"decision": "confirm"}, "ch") == "All devices turned OFF"
    engine.confirm_pending.assert_called_once_with("ch", None, source="agent")

    assert (
        runtime.execute_tool("respond_to_pending_action", {"decision": "cancel", "token": "abc123"}, "ch")
        == "Cancelled pending action `abc123`."
    )
    engine.cancel_pending.assert_called_once_with("ch", "abc123")

    assert "decision must be" in runtime.execute_tool("respond_to_pending_action", {}, "ch")


@pytest.mark.asyncio
async def test_runtime_invalid_tool_json_is_surfaced(tmp_path):
    """Malformed tool arguments should not crash the loop."""
    memory = AgentMemory(str(tmp_path / "agent.db"))
    client = MagicMock()
    tool_call = MagicMock()
    tool_call.id = "call-1"
    tool_call.function.name = "get_device_status"
    tool_call.function.arguments = "{not-json"
    first = MagicMock()
    first.choices[0].message.content = None
    first.choices[0].message.tool_calls = [tool_call]
    second = MagicMock()
    second.choices[0].message.content = "I could not read that tool call."
    second.choices[0].message.tool_calls = None
    client.chat.completions.create.side_effect = [first, second]
    runtime = AgentRuntime(client=client, model="test-model", memory=memory, action_engine=MagicMock())
    result = await runtime.process("status please", channel_id="ch")
    assert "could not read" in result
    tool_msg = client.chat.completions.create.call_args_list[1].kwargs["messages"][-2]
    assert "Invalid tool JSON" in tool_msg["content"]


@pytest.mark.asyncio
async def test_llm_summarize_rewrites_folded_notes(tmp_path, monkeypatch):
    """Optional LLM summary pass should replace the folded notes."""
    monkeypatch.setattr("waterbot.agent.runtime.AGENT_LLM_SUMMARIZE", True)
    monkeypatch.setattr("waterbot.agent.memory.AGENT_CONTEXT_MESSAGE_LIMIT", 2)
    memory = AgentMemory(str(tmp_path / "agent.db"))
    memory.record_message("ch", "user", "first", author_name="Fran")
    memory.record_message("ch", "assistant", "ack", author_name="WaterBot")
    client = MagicMock()
    rewrite = MagicMock()
    rewrite.choices[0].message.content = "Devices: pump\nWatering events:\n- folded"
    rewrite.choices[0].message.tool_calls = None
    reply = MagicMock()
    reply.choices[0].message.content = "Noted."
    reply.choices[0].message.tool_calls = None
    client.chat.completions.create.side_effect = [rewrite, reply]
    runtime = AgentRuntime(client=client, model="test-model", memory=memory)
    result = await runtime.process("second question", channel_id="ch")
    assert result == "Noted."
    assert "folded" in memory.get_context("ch")["summary"]["summary"]
