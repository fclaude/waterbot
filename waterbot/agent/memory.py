"""SQLite-backed memory and audit history for WaterBot."""

from __future__ import annotations

import json
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
    AGENT_SUMMARY_MAX_CHARS,
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
    ) -> None:
        """Record a Discord or assistant message and refresh channel summary."""
        created_at = _now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO messages (channel_id, author_id, author_name, role, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (channel_id, author_id, author_name, role, content, created_at),
            )
        self._fold_old_messages_into_summary(channel_id)
        self.prune_old_messages()

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
        return {
            "summary": dict(summary_row) if summary_row else {"summary": "", "updated_at": None},
            "recent_messages": recent,
            "pending_confirmations": self.get_pending_confirmations(channel_id),
            "recent_actions": self.get_recent_action_events(channel_id, limit=5),
            "recent_feedback": self.get_recent_feedback(channel_id=channel_id, limit=5),
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

    def _fold_old_messages_into_summary(self, channel_id: str) -> None:
        """Move messages older than the recent window into a rolling summary."""
        keep = max(AGENT_CONTEXT_MESSAGE_LIMIT, 1)
        with self._connection() as connection:
            total = connection.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()["count"]
            if total <= keep:
                return

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
                return

            existing = connection.execute(
                "SELECT summary FROM channel_summaries WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()
            existing_summary = existing["summary"] if existing else ""

            folded_lines = []
            for row in older_rows:
                speaker = row["author_name"] or row["role"]
                content = " ".join(str(row["content"]).split())
                if len(content) > 160:
                    content = content[:157] + "..."
                folded_lines.append(f"{speaker}: {content}")

            combined = (existing_summary + "\n" if existing_summary else "") + "\n".join(folded_lines)
            summary = combined[-AGENT_SUMMARY_MAX_CHARS:].lstrip()
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


def _now() -> str:
    """Return an ISO timestamp for persisted rows."""
    return datetime.now().isoformat(timespec="seconds")
