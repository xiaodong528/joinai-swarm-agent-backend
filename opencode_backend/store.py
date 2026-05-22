from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
import json
import os
import sqlite3
import uuid


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def default_database_path() -> str:
    url = os.getenv("CHAT_DATABASE_URL")
    if not url:
        return "opencode_backend.db"
    if url.startswith("sqlite:///"):
        return url.removeprefix("sqlite:///")
    if url.startswith("sqlite://"):
        return url.removeprefix("sqlite://")
    return url


@dataclass(frozen=True)
class ChatSessionRow:
    id: str
    owner_id: str
    title: str
    status: str
    scope: str
    workspace_path: str | None
    config_json: dict[str, Any]
    provider_json: dict[str, Any] | None
    launch_json: dict[str, Any]
    a2a_json: dict[str, Any]
    mcp_json: dict[str, Any]
    agent_config_json: dict[str, Any]
    skills_json: list[dict[str, Any]]
    agents_json: list[dict[str, Any]]
    opencode_session_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ChatMessageRow:
    id: str
    session_id: str
    role: str
    content: str
    a2a_message_json: dict[str, Any] | None
    created_at: str


@dataclass(frozen=True)
class ChatRunRow:
    id: str
    session_id: str
    status: str
    user_message_id: str
    assistant_message_id: str | None
    stdout: str
    stderr: str
    error: str | None
    a2a_task_json: dict[str, Any] | None
    ag_ui_events_json: list[dict[str, Any]]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SandboxBindingRow:
    session_id: str
    sandbox_id: str
    home_dir: str
    status: str
    last_used_at: str
    expires_at: str


class ChatStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or default_database_path()
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.init()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    workspace_path TEXT,
                    config_json TEXT NOT NULL,
                    provider_json TEXT,
                    launch_json TEXT NOT NULL,
                    a2a_json TEXT NOT NULL DEFAULT '{}',
                    mcp_json TEXT NOT NULL,
                    agent_config_json TEXT NOT NULL,
                    skills_json TEXT NOT NULL,
                    agents_json TEXT NOT NULL,
                    opencode_session_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_owner
                    ON chat_sessions(owner_id, updated_at);

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    a2a_message_json TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session
                    ON chat_messages(session_id, created_at);

                CREATE TABLE IF NOT EXISTS chat_runs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    user_message_id TEXT NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
                    assistant_message_id TEXT REFERENCES chat_messages(id) ON DELETE SET NULL,
                    stdout TEXT NOT NULL DEFAULT '',
                    stderr TEXT NOT NULL DEFAULT '',
                    error TEXT,
                    a2a_task_json TEXT,
                    ag_ui_events_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_runs_session
                    ON chat_runs(session_id, created_at);

                CREATE TABLE IF NOT EXISTS sandbox_bindings (
                    session_id TEXT PRIMARY KEY REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    sandbox_id TEXT NOT NULL,
                    home_dir TEXT NOT NULL,
                    status TEXT NOT NULL,
                    last_used_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(conn, "chat_sessions", "a2a_json", "TEXT NOT NULL DEFAULT '{}'")

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        definition: str,
    ) -> None:
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def create_session(self, owner_id: str, payload: dict[str, Any]) -> ChatSessionRow:
        now = utc_now()
        session_id = new_id("sess")
        title = payload.get("title") or "New chat"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions (
                    id, owner_id, title, status, scope, workspace_path, config_json,
                    provider_json, launch_json, a2a_json, mcp_json, agent_config_json, skills_json,
                    agents_json, opencode_session_id, created_at, updated_at
                )
                VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    session_id,
                    owner_id,
                    title,
                    payload["scope"],
                    payload.get("workspace_path"),
                    _dump(payload.get("config", {})),
                    _dump(payload.get("provider")) if payload.get("provider") else None,
                    _dump(payload.get("launch", {})),
                    _dump(payload.get("a2a", {})),
                    _dump(payload.get("mcp", {})),
                    _dump(payload.get("agent_config", {})),
                    _dump(payload.get("skills", [])),
                    _dump(payload.get("agents", [])),
                    now,
                    now,
                ),
            )
        return self.get_session(owner_id, session_id)

    def get_session(self, owner_id: str, session_id: str) -> ChatSessionRow:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM chat_sessions WHERE owner_id = ? AND id = ? AND status != 'deleted'",
                (owner_id, session_id),
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return _session_row(row)

    def list_sessions(self, owner_id: str) -> list[ChatSessionRow]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM chat_sessions
                WHERE owner_id = ? AND status != 'deleted'
                ORDER BY updated_at DESC
                """,
                (owner_id,),
            ).fetchall()
        return [_session_row(row) for row in rows]

    def soft_delete_session(self, owner_id: str, session_id: str) -> None:
        now = utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE chat_sessions SET status = 'deleted', updated_at = ?
                WHERE owner_id = ? AND id = ?
                """,
                (now, owner_id, session_id),
            )
            conn.execute(
                "UPDATE sandbox_bindings SET status = 'released' WHERE session_id = ?",
                (session_id,),
            )
        if cursor.rowcount == 0:
            raise KeyError(session_id)

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        a2a_message_json: dict[str, Any] | None = None,
    ) -> ChatMessageRow:
        now = utc_now()
        message_id = new_id("msg")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (id, session_id, role, content, a2a_message_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    session_id,
                    role,
                    content,
                    _dump(a2a_message_json) if a2a_message_json else None,
                    now,
                ),
            )
            conn.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
        return self.get_message(message_id)

    def get_message(self, message_id: str) -> ChatMessageRow:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
        if row is None:
            raise KeyError(message_id)
        return _message_row(row)

    def list_messages(self, session_id: str) -> list[ChatMessageRow]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM chat_messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [_message_row(row) for row in rows]

    def has_active_run(self, session_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM chat_runs
                WHERE session_id = ? AND status IN ('queued', 'running')
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return row is not None

    def create_run(self, session_id: str, user_message_id: str) -> ChatRunRow:
        now = utc_now()
        run_id = new_id("run")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_runs (
                    id, session_id, status, user_message_id, stdout, stderr,
                    ag_ui_events_json, created_at, updated_at
                )
                VALUES (?, ?, 'queued', ?, '', '', '[]', ?, ?)
                """,
                (run_id, session_id, user_message_id, now, now),
            )
        return self.get_run(session_id, run_id)

    def get_run(self, session_id: str, run_id: str) -> ChatRunRow:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM chat_runs WHERE session_id = ? AND id = ?",
                (session_id, run_id),
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return _run_row(row)

    def list_runs(self, session_id: str) -> list[ChatRunRow]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM chat_runs WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        return [_run_row(row) for row in rows]

    def update_run(
        self,
        run_id: str,
        *,
        status: str,
        stdout: str = "",
        stderr: str = "",
        error: str | None = None,
        assistant_message_id: str | None = None,
        a2a_task_json: dict[str, Any] | None = None,
        ag_ui_events_json: list[dict[str, Any]] | None = None,
    ) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE chat_runs
                SET status = ?, stdout = ?, stderr = ?, error = ?,
                    assistant_message_id = COALESCE(?, assistant_message_id),
                    a2a_task_json = ?, ag_ui_events_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    stdout,
                    stderr,
                    error,
                    assistant_message_id,
                    _dump(a2a_task_json) if a2a_task_json else None,
                    _dump(ag_ui_events_json or []),
                    now,
                    run_id,
                ),
            )

    def update_opencode_session_id(self, session_id: str, opencode_session_id: str | None) -> None:
        if not opencode_session_id:
            return
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE chat_sessions SET opencode_session_id = ?, updated_at = ? WHERE id = ?",
                (opencode_session_id, now, session_id),
            )

    def upsert_binding(self, binding: SandboxBindingRow) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sandbox_bindings (
                    session_id, sandbox_id, home_dir, status, last_used_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    sandbox_id = excluded.sandbox_id,
                    home_dir = excluded.home_dir,
                    status = excluded.status,
                    last_used_at = excluded.last_used_at,
                    expires_at = excluded.expires_at
                """,
                (
                    binding.session_id,
                    binding.sandbox_id,
                    binding.home_dir,
                    binding.status,
                    binding.last_used_at,
                    binding.expires_at,
                ),
            )

    def get_binding(self, session_id: str) -> SandboxBindingRow | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sandbox_bindings WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return SandboxBindingRow(**dict(row))

    def release_binding(self, session_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE sandbox_bindings SET status = 'released' WHERE session_id = ?",
                (session_id,),
            )


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=False)


def _load(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value)


def _session_row(row: sqlite3.Row) -> ChatSessionRow:
    data = dict(row)
    return ChatSessionRow(
        id=data["id"],
        owner_id=data["owner_id"],
        title=data["title"],
        status=data["status"],
        scope=data["scope"],
        workspace_path=data["workspace_path"],
        config_json=_load(data["config_json"], {}),
        provider_json=_load(data["provider_json"], None),
        launch_json=_load(data["launch_json"], {}),
        a2a_json=_load(data["a2a_json"], {}),
        mcp_json=_load(data["mcp_json"], {}),
        agent_config_json=_load(data["agent_config_json"], {}),
        skills_json=_load(data["skills_json"], []),
        agents_json=_load(data["agents_json"], []),
        opencode_session_id=data["opencode_session_id"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


def _message_row(row: sqlite3.Row) -> ChatMessageRow:
    data = dict(row)
    return ChatMessageRow(
        id=data["id"],
        session_id=data["session_id"],
        role=data["role"],
        content=data["content"],
        a2a_message_json=_load(data["a2a_message_json"], None),
        created_at=data["created_at"],
    )


def _run_row(row: sqlite3.Row) -> ChatRunRow:
    data = dict(row)
    return ChatRunRow(
        id=data["id"],
        session_id=data["session_id"],
        status=data["status"],
        user_message_id=data["user_message_id"],
        assistant_message_id=data["assistant_message_id"],
        stdout=data["stdout"],
        stderr=data["stderr"],
        error=data["error"],
        a2a_task_json=_load(data["a2a_task_json"], None),
        ag_ui_events_json=_load(data["ag_ui_events_json"], []),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )
