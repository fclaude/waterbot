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
    assert "Long-term channel summary" in sent_messages[0]["content"]
    assert any(
        msg.get("role") == "user" and "what is the pump doing?" in msg.get("content", "") for msg in sent_messages
    )


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
    tool_call.function.name = "execute_action"
    tool_call.function.arguments = '{"action_type":"all_on","arguments":{"timeout":120}}'

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
        "all_on",
        {"timeout": 120},
        source="agent",
        channel_id="channel-1",
        require_confirmation=True,
    )
    assert client.chat.completions.create.call_count == 2
