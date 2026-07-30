"""OpenAI integration for WaterBot with tool support."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from .agent.runtime import get_agent_tools
from .services import get_action_engine, get_agent_memory, get_agent_runtime, get_openai_client

logger = logging.getLogger("waterbot.openai")


def get_available_tools() -> List[Dict[str, Any]]:
    """Define the tools available to the OpenAI model."""
    return get_agent_tools()


def get_legacy_available_tools() -> List[Dict[str, Any]]:
    """Compatibility wrapper; prefer get_available_tools()."""
    return get_agent_tools()


# Module alias kept for older tests that patch `waterbot.openai_integration.client`.
client = get_openai_client()


def execute_tool_call(
    function_name: str,
    arguments: Dict[str, Any],
    channel_id: str = "default",
    source: str = "tool_direct",
    require_confirmation: bool = False,
) -> str:
    """Execute a tool function call and return the result."""
    try:
        if function_name == "get_recent_context":
            return json.dumps(get_agent_memory().get_context(channel_id), indent=2)

        action_engine = get_action_engine()

        if function_name == "preview_action":
            preview = action_engine.preview_action(arguments["action_type"], arguments.get("arguments", {}))
            return preview.message

        if function_name == "execute_action":
            action_type = arguments["action_type"]
            action_arguments = arguments.get("arguments", {})
        else:
            action_type = function_name
            action_arguments = dict(arguments)
            if function_name == "record_user_feedback":
                action_arguments["channel_id"] = channel_id

        action_result = action_engine.execute_action(
            action_type,
            action_arguments,
            source=source,
            channel_id=channel_id,
            require_confirmation=require_confirmation,
        )
        if action_result.message == f"Unknown action: {function_name}":
            return f"Unknown function: {function_name}"
        return action_result.message

    except Exception as e:
        logger.error("Error executing tool call %s: %s", function_name, e, exc_info=True)
        return f"Error executing {function_name}: {str(e)}"


async def process_with_openai(
    message: str,
    channel_id: str = "default",
    author_id: str | None = None,
    author_name: str | None = None,
) -> str:
    """Process a message using the shared conversational agent runtime."""
    # Prefer an explicitly patched module client in tests; otherwise use shared client.
    active_client = client if client is not None else get_openai_client()
    if not active_client:
        return "OpenAI is not configured. Please set OPENAI_API_KEY in your .env file."

    try:
        runtime = get_agent_runtime()
        # If tests patched the module client, make sure the shared runtime uses it.
        if runtime.client is not active_client:
            runtime.client = active_client
        return await runtime.process(message, channel_id, author_id, author_name)

    except Exception as e:
        logger.error("Error processing OpenAI request: %s", e, exc_info=True)
        return f"Sorry, I encountered an error processing your request: {str(e)}"
