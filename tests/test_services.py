"""Tests for shared process services."""

from unittest.mock import MagicMock, patch

from waterbot.agent.memory import AgentMemory
from waterbot.services import (
    get_action_engine,
    get_agent_memory,
    get_agent_runtime,
    get_openai_client,
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


def test_get_openai_client_uses_base_url():
    """Client construction should pass OPENAI_BASE_URL to the OpenAI SDK."""
    reset_services()
    mock_openai_cls = MagicMock()

    with (
        patch("waterbot.config.OPENAI_API_KEY", "sk-test"),
        patch("waterbot.config.OPENAI_BASE_URL", "http://127.0.0.1:8080/v1"),
        patch("waterbot.config.is_openai_configured", return_value=True),
        patch("openai.OpenAI", mock_openai_cls),
    ):
        client = get_openai_client()

    assert client is mock_openai_cls.return_value
    mock_openai_cls.assert_called_once_with(
        api_key="sk-test",
        base_url="http://127.0.0.1:8080/v1",
    )
    reset_services()


def test_get_openai_client_base_url_without_api_key():
    """Self-hosted servers can enable the client with only OPENAI_BASE_URL."""
    reset_services()
    mock_openai_cls = MagicMock()

    with (
        patch("waterbot.config.OPENAI_API_KEY", None),
        patch("waterbot.config.OPENAI_BASE_URL", "http://ollama.local/v1"),
        patch("waterbot.config.is_openai_configured", return_value=True),
        patch("openai.OpenAI", mock_openai_cls),
    ):
        client = get_openai_client()

    assert client is mock_openai_cls.return_value
    mock_openai_cls.assert_called_once_with(
        api_key="not-needed",
        base_url="http://ollama.local/v1",
    )
    reset_services()


def test_get_openai_client_default_openai_endpoint():
    """Without OPENAI_BASE_URL, the SDK default OpenAI endpoint is used."""
    reset_services()
    mock_openai_cls = MagicMock()

    with (
        patch("waterbot.config.OPENAI_API_KEY", "sk-live"),
        patch("waterbot.config.OPENAI_BASE_URL", None),
        patch("waterbot.config.is_openai_configured", return_value=True),
        patch("openai.OpenAI", mock_openai_cls),
    ):
        client = get_openai_client()

    assert client is mock_openai_cls.return_value
    mock_openai_cls.assert_called_once_with(api_key="sk-live")
    reset_services()
