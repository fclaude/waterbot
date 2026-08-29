"""Per-author sliding-window rate limit for LLM calls."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict


class SlidingWindowRateLimiter:
    """Allow at most ``max_events`` calls per ``window_seconds`` for each key."""

    def __init__(self, max_events: int, window_seconds: float = 60.0) -> None:
        """Initialize the limiter."""
        self._max_events = max(1, max_events)
        self._window_seconds = window_seconds
        self._events: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Record an event for ``key`` and return True when it is under the cap."""
        now = time.monotonic()
        with self._lock:
            queue = self._events.setdefault(key, deque())
            while queue and now - queue[0] > self._window_seconds:
                queue.popleft()
            if len(queue) >= self._max_events:
                return False
            queue.append(now)
            return True
