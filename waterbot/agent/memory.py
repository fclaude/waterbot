"""SQLite-backed memory and audit history for WaterBot."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from secrets import token_hex
from typing import Any, Dict, Iterator, List, Optional

from ..config import (
    AGENT_CONFIRMATION_TIMEOUT_MINUTES,
    AGENT_DB_FILE,
    AGENT_MEMORY_RETENTION_DAYS,
)


class AgentMemory:
    """Persist conversation context, confirmations, and action history."""

    def __init__(self, path: str = AGENT_DB_FILE) -> None:
        """Initialize the memory store."""
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Open a SQLite connection and close it after use."""
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        """Create tables if they do not exist."""
        with self._connection() as connection:
            connection.executescript(
                """
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
                """
            )

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
        self._update_channel_summary(channel_id)
        self.prune_old_messages()

    def get_context(self, channel_id: str, limit: int = 12) -> Dict[str, Any]:
        """Return summary and recent messages for prompt context."""
        with self._connection() as connection:
            summary_row = connection.execute(
                "SELECT summary, updated_at FROM channel_summaries WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()
            rows = connection.execute(
                """
                SELECT role, author_name, content, created_at
                FROM messages
                WHERE channel_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (channel_id, limit),
            ).fetchall()

        recent = [dict(row) for row in reversed(rows)]
        return {
            "summary": dict(summary_row) if summary_row else {"summary": "", "updated_at": None},
            "recent_messages": recent,
        }

    def _update_channel_summary(self, channel_id: str) -> None:
        """Maintain a compact rolling text summary for the channel."""
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT role, author_name, content
                FROM messages
                WHERE channel_id = ?
                ORDER BY id DESC
                LIMIT 30
                """,
                (channel_id,),
            ).fetchall()

            lines = []
            for row in reversed(rows):
                speaker = row["author_name"] or row["role"]
                content = " ".join(str(row["content"]).split())
                if len(content) > 220:
                    content = content[:217] + "..."
                lines.append(f"{speaker}: {content}")

            summary = "\n".join(lines)[-6000:]
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

    def get_recent_feedback(self, device: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Return recent user feedback."""
        query = "SELECT * FROM feedback"
        params: List[Any] = []
        if device:
            query += " WHERE device = ?"
            params.append(device)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connection() as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]

    def prune_old_messages(self) -> None:
        """Remove raw messages older than the configured retention period."""
        cutoff = (datetime.now() - timedelta(days=AGENT_MEMORY_RETENTION_DAYS)).isoformat(timespec="seconds")
        with self._connection() as connection:
            connection.execute("DELETE FROM messages WHERE created_at < ?", (cutoff,))


def _now() -> str:
    """Return an ISO timestamp for persisted rows."""
    return datetime.now().isoformat(timespec="seconds")
