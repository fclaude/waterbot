"""Shared pytest fixtures for WaterBot."""

import pytest

from waterbot.agent.runtime import reset_rate_limiter


@pytest.fixture(autouse=True)
def _reset_agent_rate_limiter() -> None:
    """Keep the process-wide LLM rate limiter from leaking across tests."""
    reset_rate_limiter()
    yield
    reset_rate_limiter()
