"""Scope and output guards for the conversational agent."""

from __future__ import annotations

import re
from typing import Optional

from ..config import AGENT_MAX_REPLY_CHARS

REFUSAL_MESSAGE = (
    "I only help with watering and garden device control — schedules, cycles, "
    "device on/off, and why a watering ran or was skipped. I will not generate "
    "code, exploits, or anything outside that."
)

RATE_LIMIT_MESSAGE = "Please slow down — I can only handle a few requests per minute."

_OFF_TOPIC = re.compile(
    r"(?is)("
    r"write\s+(me\s+)?(a\s+|some\s+)?(python|javascript|typescript|bash|shell|script|exploit|malware|payload)"
    r"|generate\s+(me\s+)?(code|a\s+script|an\s+exploit)"
    r"|ignore\s+(all\s+)?(previous|prior|your)\s+(instructions|rules|prompt)"
    r"|jailbreak"
    r"|you\s+are\s+now\s+(a\s+|an\s+)?(unrestricted|dan|developer\s+mode)"
    r"|show\s+(me\s+)?(your\s+)?(system\s+prompt|hidden\s+instructions)"
    r"|sudo\s+rm\s+-rf"
    r")"
)

_CODE_FENCE = re.compile(
    r"```(?:python|py|javascript|js|ts|bash|sh|shell|ruby|go|rust|java|cpp|c\+\+|php)\b",
    re.IGNORECASE,
)
_CODE_BODY = re.compile(
    r"(?m)^(import\s+\w+|from\s+\w+\s+import|def\s+\w+\s*\(|class\s+\w+\s*[:(]|#!/bin/)",
)


def is_disallowed_request(message: str) -> bool:
    """Return True when the user is asking for off-topic or abusive work."""
    return bool(_OFF_TOPIC.search(message or ""))


def looks_like_code_dump(text: str) -> bool:
    """Return True when a model reply looks like generated source code."""
    if not text:
        return False
    if _CODE_FENCE.search(text):
        return True
    return len(_CODE_BODY.findall(text)) >= 2


def gate_assistant_reply(text: Optional[str]) -> str:
    """Clamp, refuse code dumps, and never ship empty tool JSON to the user."""
    content = (text or "").strip()
    if not content:
        return "I completed the requested garden action."
    if looks_like_code_dump(content):
        return REFUSAL_MESSAGE
    if content.startswith("{") and ("tool_calls" in content or '"function"' in content):
        return REFUSAL_MESSAGE
    max_chars = max(AGENT_MAX_REPLY_CHARS, 80)
    if len(content) > max_chars:
        trimmed = content[: max_chars - 1].rsplit(" ", 1)[0]
        return (trimmed or content[: max_chars - 1]) + "…"
    return content
