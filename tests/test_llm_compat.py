"""Tests for OpenAI Chat Completions compatibility helpers."""

import pytest

from waterbot.llm_compat import (
    completion_token_limit_kwargs,
    reasoning_effort_kwargs,
    uses_max_completion_tokens,
)


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-4o-mini", False),
        ("gpt-4o", False),
        ("openai/gpt-4o-mini", False),
        ("gpt-5", True),
        ("gpt-5-mini", True),
        ("openai/gpt-5-nano", True),
        ("gpt-5.6-luna", True),
        ("o1-preview", True),
        ("o3-mini", True),
        ("o4-mini", True),
    ],
)
def test_uses_max_completion_tokens(model: str, expected: bool) -> None:
    """Model families should pick the correct token-limit parameter."""
    assert uses_max_completion_tokens(model) is expected


@pytest.mark.parametrize(
    ("model", "limit", "expected_key"),
    [
        ("gpt-4o-mini", 600, "max_tokens"),
        ("gpt-5", 600, "max_completion_tokens"),
        ("o3-mini", 400, "max_completion_tokens"),
    ],
)
def test_completion_token_limit_kwargs(model: str, limit: int, expected_key: str) -> None:
    """Token limit kwargs should use the parameter the model accepts."""
    kwargs = completion_token_limit_kwargs(model, limit)
    assert kwargs == {expected_key: limit}


@pytest.mark.parametrize(
    ("model", "use_tools", "expected"),
    [
        ("gpt-4o-mini", True, {}),
        ("gpt-5", False, {}),
        ("gpt-5", True, {"reasoning_effort": "none"}),
        ("gpt-5.6-luna", True, {"reasoning_effort": "none"}),
        ("o3-mini", True, {"reasoning_effort": "none"}),
    ],
)
def test_reasoning_effort_kwargs(model: str, use_tools: bool, expected: dict[str, str]) -> None:
    """Reasoning models need reasoning_effort='none' to use function tools."""
    assert reasoning_effort_kwargs(model, use_tools) == expected
