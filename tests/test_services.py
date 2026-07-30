"""Tests for shared process services."""

from waterbot.agent.memory import AgentMemory
from waterbot.services import (
    get_action_engine,
    get_agent_memory,
    get_agent_runtime,
    reset_services,
    set_agent_memory,
    set_openai_client,
)


def test_shared_services_reuse_memory_and_engine(tmp_path):
    """Service getters should share one memory/engine instance."""
    reset_services()
    memory = AgentMemory(str(tmp_path / "agent.db"))
    set_agent_memory(memory)
    set_openai_client(None)

    assert get_agent_memory() is memory
    engine = get_action_engine()
    assert engine.memory is memory
    assert get_action_engine() is engine

    runtime = get_agent_runtime()
    assert runtime.memory is memory
    assert runtime.action_engine is engine
    assert get_agent_runtime() is runtime

    reset_services()
