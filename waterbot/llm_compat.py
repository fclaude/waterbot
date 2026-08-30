"""OpenAI Chat Completions API compatibility helpers."""

from __future__ import annotations


def uses_max_completion_tokens(model: str) -> bool:
    """Return True when the model expects max_completion_tokens instead of max_tokens."""
    name = model.strip().lower().split("/")[-1]
    if name.startswith(("o1", "o3", "o4")):
        return True
    # GPT-5 and newer OpenAI chat models reject max_tokens.
    return name.startswith("gpt-5")


def completion_token_limit_kwargs(model: str, limit: int) -> dict[str, int]:
    """Return the token-limit keyword args appropriate for the given model."""
    if uses_max_completion_tokens(model):
        return {"max_completion_tokens": limit}
    return {"max_tokens": limit}
