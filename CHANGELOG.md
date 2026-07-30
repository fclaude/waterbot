# Changelog

## 0.3.3 - 2026-07-30

### Added
- Optional `OPENAI_BASE_URL` for OpenAI-compatible Chat Completions servers
  (OpenRouter, vLLM, Ollama, LiteLLM, and similar). Leave unset to keep using
  OpenAI. A custom base URL alone can enable the agent for local/no-auth servers.

## 0.3.2 - 2026-07-30

### Changed
- Shared `AgentMemory` / `ActionEngine` / `AgentRuntime` via `waterbot.services`
  across Discord, web, and scheduler threads.
- Conversational agent now sends recent turns as real chat history and folds older
  turns into a long-term channel summary, with pending confirmations/feedback in
  the system prompt.
- SQLite memory uses a process lock + WAL for cross-thread safety.

## 0.3.1 - 2026-07-30

### Added
- Broader policy/scheduler coverage and integration tests for schedule→GPIO,
  weather skip/run, and confirmation flows.
- Coverage gate raised to 90%.

### Changed
- Removed stale remote branch `codex/add-configurable-relay-voltage-settings`.

## 0.3.0 - 2026-07-30

### Fixed
- Bare `on`/`off` commands are permanent again; only an explicit minute duration creates a timer.
- Discord, web, and OpenAI tool paths share `ActionEngine` for mutations, audit, and confirmations.
- Discord restart uses exponential backoff with a failure cap; config errors exit immediately.
- Logging is configured at startup instead of on import.

### Changed
- Runtime dependencies no longer require `RPi.GPIO`; install `requirements-rpi.txt` on Pi hardware.
- Split `requirements.txt` / `requirements-dev.txt` / `requirements-rpi.txt`.
- Default data paths moved under `data/` for schedules, policies, and agent memory.
- Web interface defaults to `127.0.0.1` with private schedules.
- CI tests Python 3.11–3.12 and fails on mypy/security checks.
- Coverage gate raised to 85%.

### Added
- `/healthz` endpoint on the web interface.
- Checked-in `deploy/waterbot.service` and `scripts/install-service.sh`.

## 0.2.0 - 2026-07-04

- Flexible watering policies, agent memory, web dashboard, and configurable relay polarity.
