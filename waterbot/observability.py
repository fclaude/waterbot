"""Lightweight runtime markers for external Prometheus collection."""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator

logger = logging.getLogger("observability")

STATUS_PATH = Path(os.getenv("WATERBOT_METRICS_STATUS_FILE", "data/device_status.json"))
EVENTS_PATH = Path(os.getenv("WATERBOT_METRICS_EVENTS_FILE", "data/bed_events.jsonl"))
LATENCY_PATH = Path(os.getenv("WATERBOT_METRICS_LATENCY_FILE", "data/latency_events.jsonl"))


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def record_device_transition(device: str, active: bool, source: str) -> None:
    """Persist the latest device state and append a run event."""
    normalized_device = device.strip().lower()
    if not normalized_device or normalized_device == "all":
        return

    timestamp = time.time()
    payload = {
        "device": normalized_device,
        "active": bool(active),
        "source": source,
        "timestamp": timestamp,
    }

    try:
        _ensure_parent(STATUS_PATH)
        status: Dict[str, Any] = {}
        if STATUS_PATH.exists():
            status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        status[normalized_device] = payload
        STATUS_PATH.write_text(json.dumps(status, indent=2, sort_keys=True), encoding="utf-8")

        _ensure_parent(EVENTS_PATH)
        with EVENTS_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError as exc:
        logger.warning("Could not record device metrics for %s: %s", normalized_device, exc)


def record_latency(op: str, duration_seconds: float, **fields: Any) -> None:
    """Append one latency sample so it can be turned into histograms/gauges downstream.

    `op` names the stage being measured (e.g. "llm_call", "tool_call",
    "agent_turn", "discord_reply"); extra keyword fields (channel_id, model,
    tool, round, status, ...) are recorded alongside it as labels.
    """
    payload: Dict[str, Any] = {
        "op": op,
        "duration_seconds": round(max(duration_seconds, 0.0), 4),
        "timestamp": time.time(),
        **fields,
    }
    try:
        _ensure_parent(LATENCY_PATH)
        with LATENCY_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
    except OSError as exc:
        logger.warning("Could not record latency for %s: %s", op, exc)


@contextmanager
def time_operation(op: str, **fields: Any) -> Iterator[None]:
    """Context manager that records how long the wrapped block took.

    Tags the sample with status="ok" or status="error" (re-raising) so slow
    or failing stages are both visible without separate instrumentation.
    """
    start = time.monotonic()
    status = "ok"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        record_latency(op, time.monotonic() - start, status=status, **fields)
