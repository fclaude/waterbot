"""Bypass the LLM for explicit watering commands so confirmations stay reliable."""

from __future__ import annotations

from typing import FrozenSet, Optional

from ..actions import ActionEngine
from ..utils.command_parser import parse_command
from .memory import AgentMemory

# Parsed commands that must not go through the model. Unknown text still does.
_CONFIRM_ALIASES: FrozenSet[str] = frozenset({"confirm", "yes", "ok"})
_CANCEL_ALIASES: FrozenSet[str] = frozenset({"cancel", "no", "abort"})

LLM_BYPASS_COMMANDS: FrozenSet[str] = frozenset(
    {
        "confirm",
        "cancel",
        "status",
        "device_on",
        "device_off",
        "all_on",
        "all_off",
        "error",
    }
)


def try_direct_command(
    text: str,
    *,
    action_engine: ActionEngine,
    channel_id: str,
    source: str,
    author_id: Optional[str] = None,
    author_name: Optional[str] = None,
    memory: Optional[AgentMemory] = None,
) -> Optional[str]:
    """Run a parsed watering command without calling the LLM.

    Returns the reply string, or None when the line should go to the agent.
    """
    normalized = text.strip().lower()
    if memory is not None:
        alias_reply = _resolve_confirmation_alias(
            normalized,
            action_engine=action_engine,
            channel_id=channel_id,
            memory=memory,
        )
        if alias_reply is not None:
            memory.record_message(channel_id, "user", text, author_id, author_name)
            memory.record_message(channel_id, "assistant", alias_reply, author_name="WaterBot")
            return alias_reply

    command_type, params = parse_command(normalized)
    if command_type not in LLM_BYPASS_COMMANDS:
        return None

    if command_type == "error":
        reply = str(params.get("message") or "Unknown device.")
    elif command_type == "confirm":
        reply = action_engine.confirm(params["token"], channel_id=channel_id).message
    elif command_type == "cancel":
        reply = action_engine.cancel(params["token"], channel_id=channel_id).message
    else:
        result = action_engine.execute_action(
            command_type,
            params,
            source=source,
            channel_id=channel_id,
            require_confirmation=False,
        )
        reply = result.message
        if memory is not None:
            memory.update_slots_from_action(channel_id, command_type, params, result.status)

    if memory is not None:
        memory.record_message(channel_id, "user", text, author_id, author_name)
        memory.record_message(channel_id, "assistant", reply, author_name="WaterBot")
    return reply


def _resolve_confirmation_alias(
    normalized: str,
    *,
    action_engine: ActionEngine,
    channel_id: str,
    memory: AgentMemory,
) -> Optional[str]:
    """Map bare confirm/cancel replies to a single pending token when unambiguous."""
    if normalized in _CONFIRM_ALIASES:
        action = action_engine.confirm
        verb = "confirm"
    elif normalized in _CANCEL_ALIASES:
        action = action_engine.cancel
        verb = "cancel"
    else:
        return None

    pending = memory.get_pending_confirmations(channel_id)
    if len(pending) == 1:
        return action(pending[0]["token"], channel_id=channel_id).message
    if len(pending) > 1:
        options = ", ".join(f"`{verb} {item['token']}`" for item in pending)
        return f"Multiple actions are pending. Reply with one of: {options}"
    return f"No pending confirmations to {verb}."
