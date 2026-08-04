"""Durable, project-scoped conversation sessions."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from coding_kid.context import ProjectInstruction, SessionContext
from coding_kid.context_manager import (
    CompactionCheckpoint,
    ContextBudget,
    ContextManager,
    ConversationSegment,
)

SCHEMA_VERSION = 1
LOG_SCHEMA_VERSION = 1
LEASE_DURATION = timedelta(hours=1)
SessionStatus = Literal["active", "closed", "deleted", "damaged"]


class SessionError(RuntimeError):
    """Base class for durable-session failures."""


class SessionCorruptError(SessionError):
    """Raised when a session log cannot be replayed safely."""


class SessionBusyError(SessionError):
    """Raised when another process owns a live session lease."""


@dataclass(frozen=True)
class SessionInfo:
    """Small query projection used by listings and selection."""

    session_id: str
    title: str
    status: SessionStatus
    model: str
    created_at: str
    updated_at: str
    last_seq: int
    damaged: bool = False


@dataclass
class SessionHandle:
    """One acquired session and its reconstructed runtime state."""

    store: SessionStore
    info: SessionInfo
    context: SessionContext
    manager: ContextManager
    todos: list[dict[str, str]]
    owner: str
    last_hash: str
    transcript_length: int
    dirty: bool = False

    def commit_state(self, *, kind: str = "state_committed") -> None:
        """Append one durable state transition after a successful mutation."""
        if self.dirty:
            raise SessionError("Session has an unsaved transition")
        delta = self.manager.conversation.transcript[self.transcript_length :]
        payload = {
            "kind": kind,
            "transcript_delta": [_segment_to_json(item) for item in delta],
            "active": [
                _segment_to_json(item) for item in self.manager.conversation.active
            ],
            "checkpoints": [
                asdict(item) for item in self.manager.conversation.checkpoints
            ],
            "todos": [dict(item) for item in self.todos],
            "context_state": _context_state_to_json(self.manager),
        }
        try:
            record = self.store._append(self, payload)
        except Exception:
            self.dirty = True
            raise
        self.last_hash = record["hash"]
        self.transcript_length = len(self.manager.conversation.transcript)
        self.info = self.store.get_session(self.info.session_id, include_deleted=True)

    def retry_save(self, *, kind: str = "state_committed") -> None:
        """Retry a transition that previously failed to reach durable storage."""
        if not self.dirty:
            return
        self.dirty = False
        try:
            self.commit_state(kind=kind)
        except Exception:
            self.dirty = True
            raise

    def record_aborted(self, user_text: str, reason: str) -> None:
        """Record an attempt without changing the resumable conversation state."""
        if self.dirty:
            return
        record = self.store._append(
            self,
            {"kind": "turn_aborted", "user_text": user_text, "reason": reason},
        )
        self.last_hash = record["hash"]

    def close(self) -> None:
        """Mark the session closed and release its writer lease."""
        self.store.close(self)


class SessionStore:
    """Own the canonical JSONL logs and rebuildable SQLite session index."""

    def __init__(
        self,
        project_root: Path,
        *,
        home: Path | None = None,
        now: callable | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.home = (home or _default_home()).resolve()
        self._now = now or (lambda: datetime.now(UTC))
        self.project_identity = _project_identity(self.project_root)
        digest = hashlib.sha256(self.project_identity.encode("utf-8")).hexdigest()[:16]
        safe_name = _safe_component(self.project_root.name or "project")
        self.project_dir = self.home / "projects" / f"{safe_name}-{digest}"
        self.sessions_dir = self.project_dir / "sessions"
        self.database_path = self.project_dir / "state.sqlite3"
        self._prepare_storage()
        self._migrate()

    def _prepare_storage(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        _restrict(self.home, 0o700)
        _restrict(self.home / "projects", 0o700)
        _restrict(self.project_dir, 0o700)
        _restrict(self.sessions_dir, 0o700)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_info (
                    version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    log_path TEXT NOT NULL UNIQUE,
                    last_seq INTEGER NOT NULL,
                    last_hash TEXT NOT NULL,
                    damaged INTEGER NOT NULL DEFAULT 0,
                    lease_owner TEXT,
                    lease_expires_at TEXT
                );
                CREATE INDEX IF NOT EXISTS sessions_updated
                    ON sessions(status, updated_at DESC);
                """
            )
            row = connection.execute("SELECT version FROM schema_info").fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_info(version) VALUES (?)", (SCHEMA_VERSION,)
                )
            elif row["version"] != SCHEMA_VERSION:
                raise SessionError(
                    f"Unsupported session database schema: {row['version']}"
                )
        _restrict(self.database_path, 0o600)

    def create(
        self,
        context: SessionContext,
        manager: ContextManager,
        todos: list[dict[str, str]],
    ) -> SessionHandle:
        session_id = str(uuid.uuid4())
        owner = _owner_token()
        timestamp = _iso(self._now())
        log_path = self.sessions_dir / f"{session_id}.jsonl"
        payload = {
            "kind": "session_created",
            "schema_version": LOG_SCHEMA_VERSION,
            "session_id": session_id,
            "project_identity": self.project_identity,
            "session_context": _session_context_to_json(context),
            "budget": asdict(manager.budget),
            "todos": [dict(item) for item in todos],
        }
        record = _make_record(0, "", timestamp, payload)
        _append_line(log_path, record)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions(
                    session_id, title, status, model, created_at, updated_at,
                    log_path, last_seq, last_hash, lease_owner, lease_expires_at
                ) VALUES (?, ?, 'active', ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    session_id,
                    "New session",
                    context.model,
                    timestamp,
                    timestamp,
                    str(log_path),
                    record["hash"],
                    owner,
                    _iso(self._now() + LEASE_DURATION),
                ),
            )
        info = self.get_session(session_id)
        return SessionHandle(
            self,
            info,
            context,
            manager,
            [dict(item) for item in todos],
            owner,
            record["hash"],
            0,
        )

    def resume(self, session_id_or_prefix: str) -> SessionHandle:
        info = self.resolve(session_id_or_prefix)
        owner = _owner_token()
        self._acquire_lease(info.session_id, owner)
        try:
            return self._replay(info.session_id, owner)
        except Exception:
            self._release_lease(info.session_id, owner)
            raise

    def continue_latest(self) -> SessionHandle:
        sessions = self.list_sessions()
        if not sessions:
            raise SessionError("No resumable sessions exist for this project")
        return self.resume(sessions[0].session_id)

    def list_sessions(self, *, include_deleted: bool = False) -> list[SessionInfo]:
        where = "" if include_deleted else "WHERE status != 'deleted'"
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM sessions {where} ORDER BY updated_at DESC"  # noqa: S608
            ).fetchall()
        return [_row_to_info(row) for row in rows]

    def get_session(
        self, session_id: str, *, include_deleted: bool = False
    ) -> SessionInfo:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None or (row["status"] == "deleted" and not include_deleted):
            raise SessionError(f"Unknown session: {session_id}")
        return _row_to_info(row)

    def resolve(self, session_id_or_prefix: str) -> SessionInfo:
        value = session_id_or_prefix.strip().casefold()
        if not value:
            raise SessionError("Session ID must not be empty")
        matches = [
            item
            for item in self.list_sessions()
            if item.session_id.casefold().startswith(value)
        ]
        if not matches:
            raise SessionError(f"Unknown session: {session_id_or_prefix}")
        if len(matches) > 1:
            raise SessionError(f"Ambiguous session prefix: {session_id_or_prefix}")
        if matches[0].damaged:
            raise SessionCorruptError(
                f"Session {matches[0].session_id} is marked damaged"
            )
        return matches[0]

    def soft_delete(self, session_id_or_prefix: str) -> SessionInfo:
        info = self.resolve(session_id_or_prefix)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET status = 'deleted', updated_at = ?, lease_owner = NULL,
                    lease_expires_at = NULL
                WHERE session_id = ?
                """,
                (_iso(self._now()), info.session_id),
            )
        return self.get_session(info.session_id, include_deleted=True)

    def close(self, handle: SessionHandle) -> None:
        if handle.dirty:
            self._release_lease(handle.info.session_id, handle.owner)
            return
        record = self._append(handle, {"kind": "session_closed"})
        handle.last_hash = record["hash"]
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET status = 'closed', lease_owner = NULL,
                    lease_expires_at = NULL
                WHERE session_id = ? AND lease_owner = ?
                """,
                (handle.info.session_id, handle.owner),
            )
        handle.info = self.get_session(handle.info.session_id)

    def _append(self, handle: SessionHandle, payload: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (handle.info.session_id,),
            ).fetchone()
            if row is None:
                raise SessionError("Session index entry disappeared")
            if row["lease_owner"] != handle.owner:
                raise SessionBusyError("Session writer lease was lost")
            if row["last_hash"] != handle.last_hash:
                raise SessionCorruptError("Session state changed outside this process")
            sequence = row["last_seq"] + 1
            timestamp = _iso(self._now())
            record = _make_record(sequence, handle.last_hash, timestamp, payload)
            _append_line(Path(row["log_path"]), record)
            title = row["title"]
            if title == "New session" and payload.get("kind") == "state_committed":
                title = _title_from_payload(payload)
            connection.execute(
                """
                UPDATE sessions
                SET title = ?, status = 'active', updated_at = ?, last_seq = ?,
                    last_hash = ?, lease_expires_at = ?
                WHERE session_id = ? AND lease_owner = ?
                """,
                (
                    title,
                    timestamp,
                    sequence,
                    record["hash"],
                    _iso(self._now() + LEASE_DURATION),
                    handle.info.session_id,
                    handle.owner,
                ),
            )
        return record

    def _acquire_lease(self, session_id: str, owner: str) -> None:
        now = _iso(self._now())
        expires = _iso(self._now() + LEASE_DURATION)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE sessions
                SET lease_owner = ?, lease_expires_at = ?, status = 'active'
                WHERE session_id = ? AND status != 'deleted' AND damaged = 0
                  AND (lease_owner IS NULL OR lease_expires_at <= ?)
                """,
                (owner, expires, session_id, now),
            )
            if cursor.rowcount != 1:
                raise SessionBusyError(
                    f"Session {session_id} is active in another process"
                )

    def _release_lease(self, session_id: str, owner: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sessions SET lease_owner = NULL, lease_expires_at = NULL
                WHERE session_id = ? AND lease_owner = ?
                """,
                (session_id, owner),
            )

    def _replay(self, session_id: str, owner: str) -> SessionHandle:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise SessionError(f"Unknown session: {session_id}")
        try:
            records = _read_records(Path(row["log_path"]))
            context, manager, todos = _restore_records(records)
        except SessionCorruptError:
            with self._connect() as connection:
                connection.execute(
                    """
                    UPDATE sessions SET damaged = 1, status = 'damaged',
                        lease_owner = NULL, lease_expires_at = NULL
                    WHERE session_id = ?
                    """,
                    (session_id,),
                )
            raise
        last = records[-1]
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sessions SET last_seq = ?, last_hash = ?, updated_at = ?
                WHERE session_id = ? AND lease_owner = ?
                """,
                (last["seq"], last["hash"], last["timestamp"], session_id, owner),
            )
        info = self.get_session(session_id)
        return SessionHandle(
            self,
            info,
            context,
            manager,
            todos,
            owner,
            last["hash"],
            len(manager.conversation.transcript),
        )


def _default_home() -> Path:
    configured = os.getenv("CODING_KID_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".coding-kid"


def _project_identity(project_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
    except (OSError, subprocess.SubprocessError):
        completed = None
    if completed is not None and completed.returncode == 0:
        candidate = completed.stdout.strip()
        if candidate:
            return os.path.normcase(str(Path(candidate).resolve()))
    return os.path.normcase(str(project_root.resolve()))


def _safe_component(value: str) -> str:
    rendered = "".join(character if character.isalnum() else "-" for character in value)
    return rendered.strip("-")[:40] or "project"


def _owner_token() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4()}"


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _restrict(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        pass


def _json_value(value: Any) -> Any:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dict__"):
        return vars(value)
    return str(value)


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_value,
    ).encode("utf-8")


def _make_record(
    sequence: int, previous_hash: str, timestamp: str, payload: dict[str, Any]
) -> dict[str, Any]:
    body = {
        "seq": sequence,
        "prev_hash": previous_hash,
        "timestamp": timestamp,
        **payload,
    }
    digest = hashlib.sha256(
        previous_hash.encode("ascii") + _canonical(body)
    ).hexdigest()
    return {**body, "hash": digest}


def _append_line(path: Path, record: dict[str, Any]) -> None:
    line = _canonical(record) + b"\n"
    with path.open("ab") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())
    _restrict(path, 0o600)


def _read_records(path: Path) -> list[dict[str, Any]]:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise SessionCorruptError(f"Could not read session log: {error}") from error
    raw_lines = data.splitlines(keepends=True)
    records: list[dict[str, Any]] = []
    previous_hash = ""
    for index, raw_line in enumerate(raw_lines):
        complete = raw_line.endswith((b"\n", b"\r"))
        try:
            record = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            if index == len(raw_lines) - 1 and not complete:
                break
            raise SessionCorruptError(
                f"Invalid JSON at log line {index + 1}"
            ) from error
        expected_seq = len(records)
        if (
            record.get("seq") != expected_seq
            or record.get("prev_hash") != previous_hash
        ):
            raise SessionCorruptError(
                f"Broken session chain at sequence {expected_seq}"
            )
        supplied_hash = record.get("hash")
        body = {key: value for key, value in record.items() if key != "hash"}
        expected_hash = hashlib.sha256(
            previous_hash.encode("ascii") + _canonical(body)
        ).hexdigest()
        if supplied_hash != expected_hash:
            raise SessionCorruptError(
                f"Invalid session hash at sequence {expected_seq}"
            )
        records.append(record)
        previous_hash = expected_hash
    if not records or records[0].get("kind") != "session_created":
        raise SessionCorruptError("Session log has no valid creation record")
    return records


def _session_context_to_json(context: SessionContext) -> dict[str, Any]:
    return {
        "cwd": str(context.cwd),
        "operating_system": context.operating_system,
        "shell": context.shell,
        "model": context.model,
        "local_date": context.local_date,
        "project_root": str(context.project_root),
        "project_instructions": [
            {
                "path": str(item.path),
                "content": item.content,
                "truncated": item.truncated,
            }
            for item in context.project_instructions
        ],
        "project_instructions_truncated": context.project_instructions_truncated,
    }


def _session_context_from_json(value: dict[str, Any]) -> SessionContext:
    return SessionContext(
        cwd=Path(value["cwd"]),
        operating_system=value["operating_system"],
        shell=value["shell"],
        model=value["model"],
        local_date=value["local_date"],
        project_root=Path(value["project_root"]),
        project_instructions=tuple(
            ProjectInstruction(
                Path(item["path"]), item["content"], bool(item["truncated"])
            )
            for item in value["project_instructions"]
        ),
        project_instructions_truncated=bool(value["project_instructions_truncated"]),
    )


def _segment_to_json(segment: ConversationSegment) -> dict[str, Any]:
    return {
        "kind": segment.kind,
        "items": json.loads(json.dumps(segment.items, default=_json_value)),
    }


def _segment_from_json(value: dict[str, Any]) -> ConversationSegment:
    return ConversationSegment(value["kind"], list(value["items"]))


def _context_state_to_json(manager: ContextManager) -> dict[str, Any]:
    return {
        "calibration_factor": manager.calibration_factor,
        "last_actual_input_tokens": manager.last_actual_input_tokens,
        "last_estimated_input_tokens": manager.last_estimated_input_tokens,
        "consecutive_auto_compaction_failures": (
            manager.consecutive_auto_compaction_failures
        ),
        "proactive_compaction_disabled": manager.proactive_compaction_disabled,
    }


def _restore_records(
    records: list[dict[str, Any]],
) -> tuple[SessionContext, ContextManager, list[dict[str, str]]]:
    header = records[0]
    if header.get("schema_version") != LOG_SCHEMA_VERSION:
        raise SessionCorruptError(
            f"Unsupported session log schema: {header.get('schema_version')}"
        )
    context = _session_context_from_json(header["session_context"])
    budget_data = header["budget"]
    manager = ContextManager(
        context,
        ContextBudget(budget_data["context_length"], budget_data["source"]),
    )
    todos = [dict(item) for item in header.get("todos", [])]
    for record in records[1:]:
        if record.get("kind") not in {"state_committed", "context_committed"}:
            continue
        manager.conversation.transcript.extend(
            _segment_from_json(item) for item in record["transcript_delta"]
        )
        manager.conversation.active = [
            _segment_from_json(item) for item in record["active"]
        ]
        manager.conversation.checkpoints = [
            CompactionCheckpoint(**item) for item in record["checkpoints"]
        ]
        state = record["context_state"]
        manager.calibration_factor = float(state["calibration_factor"])
        manager.last_actual_input_tokens = state["last_actual_input_tokens"]
        manager.last_estimated_input_tokens = state["last_estimated_input_tokens"]
        manager.consecutive_auto_compaction_failures = int(
            state["consecutive_auto_compaction_failures"]
        )
        manager.proactive_compaction_disabled = bool(
            state["proactive_compaction_disabled"]
        )
        todos = [dict(item) for item in record["todos"]]
    return context, manager, todos


def _title_from_payload(payload: dict[str, Any]) -> str:
    for segment in payload.get("transcript_delta", []):
        if segment.get("kind") != "user":
            continue
        for item in segment.get("items", []):
            content = item.get("content") if isinstance(item, dict) else None
            if isinstance(content, str) and content.strip():
                compact = " ".join(content.split())
                return compact[:77] + ("..." if len(compact) > 77 else "")
    return "New session"


def _row_to_info(row: sqlite3.Row) -> SessionInfo:
    return SessionInfo(
        session_id=row["session_id"],
        title=row["title"],
        status=row["status"],
        model=row["model"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_seq=row["last_seq"],
        damaged=bool(row["damaged"]),
    )
