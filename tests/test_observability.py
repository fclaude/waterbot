"""Tests for latency instrumentation helpers."""

import json

from waterbot import observability


def test_record_latency_appends_jsonl(tmp_path, monkeypatch):
    path = tmp_path / "latency.jsonl"
    monkeypatch.setattr(observability, "LATENCY_PATH", path)

    observability.record_latency("llm_call", 0.125, channel_id="abc", model="gpt-4o-mini")

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["op"] == "llm_call"
    assert payload["duration_seconds"] == 0.125
    assert payload["channel_id"] == "abc"
    assert payload["model"] == "gpt-4o-mini"
    assert "timestamp" in payload


def test_time_operation_records_ok_status(tmp_path, monkeypatch):
    path = tmp_path / "latency.jsonl"
    monkeypatch.setattr(observability, "LATENCY_PATH", path)

    with observability.time_operation("tool_call", tool="status"):
        pass

    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert payload["op"] == "tool_call"
    assert payload["status"] == "ok"
    assert payload["tool"] == "status"
    assert payload["duration_seconds"] >= 0


def test_time_operation_records_error_status_and_reraises(tmp_path, monkeypatch):
    path = tmp_path / "latency.jsonl"
    monkeypatch.setattr(observability, "LATENCY_PATH", path)

    try:
        with observability.time_operation("tool_call", tool="status"):
            raise ValueError("boom")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError to propagate")

    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert payload["status"] == "error"


def test_record_latency_swallows_os_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(observability, "LATENCY_PATH", tmp_path / "missing" / "nested" / "latency.jsonl")

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(observability.Path, "open", _boom)

    # Should not raise even though the underlying write fails.
    observability.record_latency("llm_call", 0.01)
