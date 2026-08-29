"""Lightweight runtime markers for external Prometheus collection."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("observability")

STATUS_PATH = Path(os.getenv("WATERBOT_METRICS_STATUS_FILE", "data/device_status.json"))
EVENTS_PATH = Path(os.getenv("WATERBOT_METRICS_EVENTS_FILE", "data/bed_events.jsonl"))


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
