"""SQLite-backed memory and audit history for WaterBot."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from secrets import token_hex
from typing import Any, Dict, Iterator, List, Optional

from ..config import (
    AGENT_CONFIRMATION_TIMEOUT_MINUTES,
    AGENT_CONTEXT_MESSAGE_LIMIT,
    AGENT_DB_FILE,
    AGENT_MEMORY_RETENTION_DAYS,
    AGENT_RECENT_ACTIONS_LIMIT,
    AGENT_SUMMARY_MAX_CHARS,
    DEVICE_TO_PIN,
)


class AgentMemory:
    """Persist conversation context, confirmations, and action history.

    Each public method opens a short-lived SQLite connection under a process lock
    so Discord, scheduler, and web threads can share one store safely.
    """

    def __init__(self, path: str = AGENT_DB_FILE) -> None:
        """Initialize the memory store."""
        self.path = path
        self._lock = threading.RLock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=30,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Open a SQLite connection and close it after use."""
        with self._lock:
            connection = self._connect()
            try:
                yield connection
                connection.commit()
            finally:
                connection.close()

    def _initialize(self) -> None:
        """Create tables if they do not exist."""
        with self._connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    author_id TEXT,
                    author_name TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS channel_summaries (
                    channel_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pending_confirmations (
                    token TEXT PRIMARY KEY,
                    channel_id TEXT,
                    action_type TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    resolved_at TEXT
                );

                CREATE TABLE IF NOT EXISTS action_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT,
                    source TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    confirmation_token TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS policy_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    policy_id TEXT NOT NULL,
                    device TEXT NOT NULL,
                    run_key TEXT NOT NULL,
                    executed INTEGER NOT NULL,
                    skipped INTEGER NOT NULL,
                    duration_minutes REAL NOT NULL,
                    message TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    matched_rules_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT,
                    device TEXT,
                    feedback TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS channel_slots (
                    channel_id TEXT PRIMARY KEY,
                    last_device TEXT,
                    last_duration_minutes REAL,
                    last_action TEXT,
                    last_policy_id TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_channel_id
                    ON messages(channel_id, id);
                CREATE INDEX IF NOT EXISTS idx_action_events_channel_id
                    ON action_events(channel_id, id);
                """)

    def record_message(
        self,
        channel_id: str,
        role: str,
        content: str,
        author_id: Optional[str] = None,
        author_name: Optional[str] = None,
    ) -> bool:
        """Record a Discord or assistant message and refresh channel summary.

        Returns True when older turns were folded into the long-term summary.
        """
        created_at = _now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO messages (channel_id, author_id, author_name, role, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (channel_id, author_id, author_name, role, content, created_at),
            )
        folded = self._fold_old_messages_into_summary(channel_id)
        self.prune_old_messages()
        return folded

    def get_context(
        self,
        channel_id: str,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return long-term summary plus recent messages for prompt context."""
        recent_limit = limit if limit is not None else AGENT_CONTEXT_MESSAGE_LIMIT
        with self._connection() as connection:
            summary_row = connection.execute(
                "SELECT summary, updated_at FROM channel_summaries WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()
            rows = connection.execute(
                """
                SELECT role, author_id, author_name, content, created_at
                FROM messages
                WHERE channel_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (channel_id, recent_limit),
            ).fetchall()

        recent = [dict(row) for row in reversed(rows)]
        action_limit = AGENT_RECENT_ACTIONS_LIMIT
        return {
            "summary": dict(summary_row) if summary_row else {"summary": "", "updated_at": None},
            "recent_messages": recent,
            "pending_confirmations": self.get_pending_confirmations(channel_id),
            "recent_actions": self.get_recent_action_events(channel_id, limit=action_limit),
            "recent_feedback": self.get_recent_feedback(channel_id=channel_id, limit=5),
            "working_slots": self.get_working_slots(channel_id),
        }

    def get_conversation_messages(
        self,
        channel_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """Return recent turns as OpenAI chat messages (user/assistant only)."""
        recent_limit = limit if limit is not None else AGENT_CONTEXT_MESSAGE_LIMIT
        context = self.get_context(channel_id, limit=recent_limit)
        conversation: List[Dict[str, str]] = []
        for item in context["recent_messages"]:
            role = item.get("role")
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            if role == "assistant":
                conversation.append({"role": "assistant", "content": content})
            elif role in {"user", "system"}:
                # Persist system-ish notes as user context lines so the model
                # still sees them in the turn stream.
                label = item.get("author_name")
                if role == "user" and label:
                    conversation.append({"role": "user", "content": content})
                elif role == "user":
                    conversation.append({"role": "user", "content": content})
                else:
                    conversation.append({"role": "user", "content": f"[{label or 'note'}] {content}"})
        return conversation

    def _fold_old_messages_into_summary(self, channel_id: str) -> bool:
        """Move messages older than the recent window into a structured summary."""
        keep = max(AGENT_CONTEXT_MESSAGE_LIMIT, 1)
        with self._connection() as connection:
            total = connection.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()["count"]
            if total <= keep:
                return False

            older_rows = connection.execute(
                """
                SELECT role, author_name, content
                FROM messages
                WHERE channel_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (channel_id, total - keep),
            ).fetchall()
            if not older_rows:
                return False

            existing = connection.execute(
                "SELECT summary FROM channel_summaries WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()
            existing_summary = existing["summary"] if existing else ""
            summary = build_structured_summary(existing_summary, [dict(row) for row in older_rows])
            summary = summary[-AGENT_SUMMARY_MAX_CHARS:].lstrip()
            connection.execute(
                """
                INSERT INTO channel_summaries (channel_id, summary, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    summary = excluded.summary,
                    updated_at = excluded.updated_at
                """,
                (channel_id, summary, _now()),
            )
            oldest_kept = connection.execute(
                """
                SELECT id FROM messages
                WHERE channel_id = ?
                ORDER BY id DESC
                LIMIT 1 OFFSET ?
                """,
                (channel_id, keep - 1),
            ).fetchone()
            if oldest_kept:
                connection.execute(
                    "DELETE FROM messages WHERE channel_id = ? AND id < ?",
                    (channel_id, oldest_kept["id"]),
                )
            return True

    def create_confirmation(
        self,
        action_type: str,
        arguments: Dict[str, Any],
        description: str,
        channel_id: Optional[str] = None,
    ) -> str:
        """Create a pending confirmation and return its token."""
        token = token_hex(3)
        now = datetime.now()
        expires_at = now + timedelta(minutes=AGENT_CONFIRMATION_TIMEOUT_MINUTES)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO pending_confirmations (
                    token, channel_id, action_type, arguments_json, description,
                    status, created_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    token,
                    channel_id,
                    action_type,
                    json.dumps(arguments, sort_keys=True),
                    description,
                    now.isoformat(timespec="seconds"),
                    expires_at.isoformat(timespec="seconds"),
                ),
            )
        return token

    def get_pending_confirmation(self, token: str, channel_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return a pending confirmation if it exists and is not expired."""
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM pending_confirmations
                WHERE token = ? AND status = 'pending'
                """,
                (token,),
            ).fetchone()

        if not row:
            return None

        confirmation = dict(row)
        if channel_id and confirmation.get("channel_id") and confirmation["channel_id"] != channel_id:
            return None
        if datetime.fromisoformat(confirmation["expires_at"]) < datetime.now():
            self.resolve_confirmation(token, "expired")
            return None

        confirmation["arguments"] = json.loads(confirmation["arguments_json"])
        return confirmation

    def get_pending_confirmations(self, channel_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return non-expired pending confirmations, optionally for one channel."""
        with self._connection() as connection:
            if channel_id:
                rows = connection.execute(
                    """
                    SELECT * FROM pending_confirmations
                    WHERE status = 'pending' AND (channel_id IS NULL OR channel_id = ?)
                    ORDER BY created_at DESC
                    """,
                    (channel_id,),
                ).fetchall()
            else:
                rows = connection.execute("""
                    SELECT * FROM pending_confirmations
                    WHERE status = 'pending'
                    ORDER BY created_at DESC
                    """).fetchall()

        pending: List[Dict[str, Any]] = []
        now = datetime.now()
        for row in rows:
            confirmation = dict(row)
            if datetime.fromisoformat(confirmation["expires_at"]) < now:
                self.resolve_confirmation(confirmation["token"], "expired")
                continue
            confirmation["arguments"] = json.loads(confirmation["arguments_json"])
            pending.append(confirmation)
        return pending

    def resolve_confirmation(self, token: str, status: str) -> None:
        """Resolve a pending confirmation."""
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE pending_confirmations
                SET status = ?, resolved_at = ?
                WHERE token = ? AND status = 'pending'
                """,
                (status, _now(), token),
            )

    def record_action_event(
        self,
        action_type: str,
        arguments: Dict[str, Any],
        status: str,
        message: str,
        source: str,
        channel_id: Optional[str] = None,
        confirmation_token: Optional[str] = None,
    ) -> None:
        """Record an action attempt/result."""
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO action_events (
                    channel_id, source, action_type, arguments_json, status,
                    message, confirmation_token, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    channel_id,
                    source,
                    action_type,
                    json.dumps(arguments, sort_keys=True),
                    status,
                    message,
                    confirmation_token,
                    _now(),
                ),
            )

    def get_recent_action_events(
        self,
        channel_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Return recent action audit events."""
        query = "SELECT * FROM action_events"
        params: List[Any] = []
        if channel_id:
            query += " WHERE channel_id = ?"
            params.append(channel_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        events = []
        for row in rows:
            event = dict(row)
            event["arguments"] = json.loads(event.pop("arguments_json"))
            events.append(event)
        return events

    def record_policy_decision(
        self,
        policy_id: str,
        device: str,
        run_key: str,
        executed: bool,
        skipped: bool,
        duration_minutes: float,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        matched_rules: Optional[List[str]] = None,
    ) -> None:
        """Record a policy decision for later explanations."""
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO policy_decisions (
                    policy_id, device, run_key, executed, skipped, duration_minutes,
                    message, context_json, matched_rules_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    policy_id,
                    device,
                    run_key,
                    int(executed),
                    int(skipped),
                    duration_minutes,
                    message,
                    json.dumps(context or {}, sort_keys=True),
                    json.dumps(matched_rules or [], sort_keys=True),
                    _now(),
                ),
            )

    def get_policy_decision_history(self, device: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Return recent policy decisions."""
        query = "SELECT * FROM policy_decisions"
        params: List[Any] = []
        if device:
            query += " WHERE device = ?"
            params.append(device)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()

        decisions = []
        for row in rows:
            decision = dict(row)
            decision["context"] = json.loads(decision.pop("context_json"))
            decision["matched_rules"] = json.loads(decision.pop("matched_rules_json"))
            decisions.append(decision)
        return decisions

    def record_feedback(
        self,
        feedback: str,
        channel_id: Optional[str] = None,
        device: Optional[str] = None,
    ) -> None:
        """Record user feedback for future agent context."""
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO feedback (channel_id, device, feedback, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (channel_id, device, feedback, _now()),
            )

    def get_recent_feedback(
        self,
        device: Optional[str] = None,
        channel_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Return recent user feedback."""
        clauses: List[str] = []
        params: List[Any] = []
        if device:
            clauses.append("device = ?")
            params.append(device)
        if channel_id:
            clauses.append("channel_id = ?")
            params.append(channel_id)
        query = "SELECT * FROM feedback"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connection() as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]

    def prune_old_messages(self) -> None:
        """Remove raw messages older than the configured retention period."""
        cutoff = (datetime.now() - timedelta(days=AGENT_MEMORY_RETENTION_DAYS)).isoformat(timespec="seconds")
        with self._connection() as connection:
            connection.execute("DELETE FROM messages WHERE created_at < ?", (cutoff,))
            connection.execute("DELETE FROM action_events WHERE created_at < ?", (cutoff,))
            connection.execute("DELETE FROM feedback WHERE created_at < ?", (cutoff,))

    def get_working_slots(self, channel_id: str) -> Dict[str, Any]:
        """Return last-device / last-duration slots for follow-up commands."""
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT last_device, last_duration_minutes, last_action, last_policy_id, updated_at
                FROM channel_slots WHERE channel_id = ?
                """,
                (channel_id,),
            ).fetchone()
        if not row:
            return {
                "last_device": None,
                "last_duration_minutes": None,
                "last_action": None,
                "last_policy_id": None,
                "updated_at": None,
            }
        return dict(row)

    def update_working_slots(
        self,
        channel_id: str,
        *,
        last_device: Optional[str] = None,
        last_duration_minutes: Optional[float] = None,
        last_action: Optional[str] = None,
        last_policy_id: Optional[str] = None,
    ) -> None:
        """Merge non-null slot fields for a channel."""
        current = self.get_working_slots(channel_id)
        device = last_device if last_device is not None else current.get("last_device")
        duration = last_duration_minutes if last_duration_minutes is not None else current.get("last_duration_minutes")
        action = last_action if last_action is not None else current.get("last_action")
        policy_id = last_policy_id if last_policy_id is not None else current.get("last_policy_id")
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO channel_slots (
                    channel_id, last_device, last_duration_minutes, last_action, last_policy_id, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    last_device = excluded.last_device,
                    last_duration_minutes = excluded.last_duration_minutes,
                    last_action = excluded.last_action,
                    last_policy_id = excluded.last_policy_id,
                    updated_at = excluded.updated_at
                """,
                (channel_id, device, duration, action, policy_id, _now()),
            )

    def replace_channel_summary(self, channel_id: str, summary: str) -> None:
        """Overwrite the long-term summary (used by optional LLM folding)."""
        clipped = summary[-AGENT_SUMMARY_MAX_CHARS:].lstrip()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO channel_summaries (channel_id, summary, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    summary = excluded.summary,
                    updated_at = excluded.updated_at
                """,
                (channel_id, clipped, _now()),
            )

    def update_slots_from_action(
        self,
        channel_id: str,
        action_type: str,
        arguments: Dict[str, Any],
        status: str,
    ) -> None:
        """Remember the last successful (or pending) watering action for follow-ups."""
        if status not in {"success", "pending_confirmation"}:
            return
        device = arguments.get("device")
        if isinstance(device, str) and device.strip():
            device_name: Optional[str] = device.strip().lower()
        elif action_type in {"all_on", "all_off"}:
            device_name = "all"
        else:
            device_name = None
        duration: Optional[float] = None
        if arguments.get("duration_minutes") is not None:
            try:
                duration = float(arguments["duration_minutes"])
            except (TypeError, ValueError):
                duration = None
        elif arguments.get("timeout") is not None:
            try:
                duration = float(arguments["timeout"]) / 60.0
            except (TypeError, ValueError):
                duration = None
        policy_arg = arguments.get("policy")
        policy = policy_arg if isinstance(policy_arg, dict) else {}
        policy_id = arguments.get("policy_id") or policy.get("id")
        self.update_working_slots(
            channel_id,
            last_device=device_name,
            last_duration_minutes=duration,
            last_action=action_type,
            last_policy_id=str(policy_id) if policy_id else None,
        )


def build_structured_summary(existing: str, rows: List[Dict[str, Any]]) -> str:
    """Fold overflow turns into labeled garden notes instead of a raw transcript dump."""
    sections = _parse_structured_summary(existing)
    device_names = {name.lower() for name in DEVICE_TO_PIN.keys()}

    for row in rows:
        speaker = str(row.get("author_name") or row.get("role") or "user")
        content = " ".join(str(row.get("content") or "").split())
        if not content:
            continue
        clipped = _clip(content, 120)
        found = [name for name in device_names if re.search(rf"\b{re.escape(name)}\b", content, re.I)]
        sections["devices"].update(found)
        lower = content.lower()
        if any(token in lower for token in ("too dry", "too wet", "feedback")):
            sections["feedback"].append(f"{speaker}: {clipped}")
        elif found or any(token in lower for token in ("on", "off", "water", "schedule", "cycle", "bed")):
            sections["events"].append(f"{speaker}: {clipped}")
        else:
            sections["other"].append(f"{speaker}: {_clip(content, 80)}")

    return _format_structured_summary(sections)


def _parse_structured_summary(text: str) -> Dict[str, Any]:
    sections: Dict[str, Any] = {
        "devices": set(),
        "events": [],
        "feedback": [],
        "other": [],
    }
    if not text or not text.strip():
        return sections
    if not text.startswith("Devices:"):
        sections["other"].append(_clip(text.replace("\n", " "), 200))
        return sections

    current = "other"
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("Devices:"):
            rest = line[len("Devices:") :].strip()
            sections["devices"].update(part.strip().lower() for part in rest.split(",") if part.strip())
            current = "devices"
        elif line.startswith("Watering events:"):
            current = "events"
        elif line.startswith("Feedback:"):
            current = "feedback"
        elif line.startswith("Other:"):
            current = "other"
        elif line.startswith("- ") and current in {"events", "feedback", "other"}:
            sections[current].append(line[2:])
    return sections


def _format_structured_summary(sections: Dict[str, Any]) -> str:
    devices = sorted(str(item) for item in sections["devices"] if item)
    events = list(sections["events"])[-20:]
    feedback = list(sections["feedback"])[-10:]
    other = list(sections["other"])[-8:]
    lines = [
        "Devices: " + (", ".join(devices) if devices else "(none yet)"),
        "Watering events:",
    ]
    lines.extend(f"- {item}" for item in events or ["(none)"])
    lines.append("Feedback:")
    lines.extend(f"- {item}" for item in feedback or ["(none)"])
    lines.append("Other:")
    lines.extend(f"- {item}" for item in other or ["(none)"])
    return "\n".join(lines)


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _now() -> str:
    """Return an ISO timestamp for persisted rows."""
    return datetime.now().isoformat(timespec="seconds")
