"""Shared process-wide services for WaterBot.

Discord (async), the scheduler thread, and the web server thread all touch
GPIO, agent memory, and confirmations. Use these getters so they share one
AgentMemory / ActionEngine / AgentRuntime instead of opening separate stores.

Thread model:
- Discord bot: asyncio event loop (main process)
- Scheduler: background thread calling GPIO + AgentMemory + Discord notify
- Web server: ThreadingHTTPServer worker threads

SQLite access is serialized inside AgentMemory. GPIO uses DeviceController's lock.
Do not share mutable schedule state across processes; one WaterBot process is assumed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .actions import ActionEngine
    from .agent.memory import AgentMemory
    from .agent.runtime import AgentRuntime

_memory: Optional[AgentMemory] = None
_action_engine: Optional[ActionEngine] = None
_agent_runtime: Optional[AgentRuntime] = None
_openai_client: Any = None


def get_agent_memory() -> AgentMemory:
    """Return the shared agent memory store."""
    global _memory
    if _memory is None:
        from .agent.memory import AgentMemory

        _memory = AgentMemory()
    return _memory


def set_agent_memory(memory: Optional[AgentMemory]) -> None:
    """Replace the shared memory (tests). Clears dependent services."""
    global _memory, _action_engine, _agent_runtime
    _memory = memory
    _action_engine = None
    _agent_runtime = None


def get_action_engine() -> ActionEngine:
    """Return the shared action engine backed by shared memory."""
    global _action_engine
    if _action_engine is None:
        from .actions import ActionEngine

        _action_engine = ActionEngine(memory=get_agent_memory())
    return _action_engine


def set_action_engine(engine: Optional[ActionEngine]) -> None:
    """Replace the shared action engine (tests)."""
    global _action_engine, _agent_runtime
    _action_engine = engine
    _agent_runtime = None


def get_openai_client() -> Any:
    """Return the shared OpenAI-compatible client when configured.

    Uses the official OpenAI SDK against api.openai.com by default, or against
    OPENAI_BASE_URL when set (any Chat Completions-compatible server).
    """
    global _openai_client
    if _openai_client is None:
        from .config import OPENAI_API_KEY, OPENAI_BASE_URL, is_openai_configured

        if is_openai_configured():
            from openai import OpenAI

            kwargs: dict[str, Any] = {
                # Self-hosted OpenAI-compatible servers often ignore auth; the SDK
                # still expects a non-empty api_key string.
                "api_key": OPENAI_API_KEY or "not-needed",
            }
            if OPENAI_BASE_URL:
                kwargs["base_url"] = OPENAI_BASE_URL
            _openai_client = OpenAI(**kwargs)
    return _openai_client


def set_openai_client(client: Any) -> None:
    """Replace the shared OpenAI client (tests)."""
    global _openai_client, _agent_runtime
    _openai_client = client
    _agent_runtime = None


def get_agent_runtime() -> AgentRuntime:
    """Return the shared conversational agent runtime."""
    global _agent_runtime
    if _agent_runtime is None:
        from .agent.runtime import AgentRuntime
        from .config import OPENAI_MODEL

        _agent_runtime = AgentRuntime(
            client=get_openai_client(),
            model=OPENAI_MODEL,
            memory=get_agent_memory(),
            action_engine=get_action_engine(),
        )
    return _agent_runtime


def set_agent_runtime(runtime: Optional[AgentRuntime]) -> None:
    """Replace the shared agent runtime (tests)."""
    global _agent_runtime
    _agent_runtime = runtime


def reset_services() -> None:
    """Clear all shared services (tests)."""
    set_agent_memory(None)
    set_openai_client(None)
    set_action_engine(None)
    set_agent_runtime(None)
