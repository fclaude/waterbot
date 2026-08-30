"""OpenAI Chat Completions API compatibility helpers."""

from __future__ import annotations


def _is_reasoning_model(model: str) -> bool:
    name = model.strip().lower().split("/")[-1]
    if name.startswith(("o1", "o3", "o4")):
        return True
    # GPT-5 and newer OpenAI chat models are reasoning models.
    return name.startswith("gpt-5")


def uses_max_completion_tokens(model: str) -> bool:
    """Return True when the model expects max_completion_tokens instead of max_tokens."""
    return _is_reasoning_model(model)


def completion_token_limit_kwargs(model: str, limit: int) -> dict[str, int]:
    """Return the token-limit keyword args appropriate for the given model."""
    if uses_max_completion_tokens(model):
        return {"max_completion_tokens": limit}
    return {"max_tokens": limit}


def reasoning_effort_kwargs(model: str, use_tools: bool) -> dict[str, str]:
    """Return reasoning_effort override needed for reasoning models called with function tools.

    Some reasoning models (e.g. the GPT-5 family) reject function tools on
    /v1/chat/completions unless reasoning_effort is explicitly set to "none".
    """
    if use_tools and _is_reasoning_model(model):
        return {"reasoning_effort": "none"}
    return {}
