from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from coding_kid.context import ProjectInstruction, SessionContext
from coding_kid.context_manager import ContextBudget, ContextManager
from coding_kid.sessions import (
    SessionBusyError,
    SessionCorruptError,
    SessionStore,
    _append_line,
    _iso,
    _make_record,
)


def make_runtime(project: Path) -> tuple[SessionContext, ContextManager]:
    context = SessionContext(
        cwd=project,
        operating_system="Test OS",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-08-04",
        project_root=project,
        project_instructions=(
            ProjectInstruction(project / "AGENTS.md", "Keep it small."),
        ),
    )
    return context, ContextManager(context, ContextBudget(32_768, "test"))


def test_session_round_trip_restores_all_canonical_state(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    context, manager = make_runtime(project)
    store = SessionStore(project, home=tmp_path / "home")
    handle = store.create(context, manager, [])

    manager.conversation.append_user("Implement ALPHA")
    manager.conversation.append_model_round(
        [{"type": "message", "content": [{"type": "text", "text": "Done"}]}]
    )
    manager.calibration_factor = 1.25
    manager.last_actual_input_tokens = 123
    handle.todos = [{"content": "Keep ALPHA", "status": "in_progress"}]
    handle.commit_state()
    session_id = handle.info.session_id
    handle.close()

    resumed = store.resume(session_id[:8])

    assert resumed.context == context
    assert (
        resumed.manager.conversation.active_items()[0]["content"] == "Implement ALPHA"
    )
    assert len(resumed.manager.conversation.transcript) == 2
    assert resumed.manager.calibration_factor == 1.25
    assert resumed.manager.last_actual_input_tokens == 123
    assert resumed.todos == [{"content": "Keep ALPHA", "status": "in_progress"}]
    assert resumed.info.title == "Implement ALPHA"


def test_sessions_are_independent_and_continue_uses_latest(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    store = SessionStore(project, home=tmp_path / "home")
    context, first_manager = make_runtime(project)
    first = store.create(context, first_manager, [])
    first.close()
    _, second_manager = make_runtime(project)
    second = store.create(context, second_manager, [])
    second.close()

    listed = store.list_sessions()
    assert {item.session_id for item in listed} == {
        first.info.session_id,
        second.info.session_id,
    }
    assert store.continue_latest().info.session_id == second.info.session_id


def test_live_lease_prevents_concurrent_resume(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    context, manager = make_runtime(project)
    store = SessionStore(project, home=tmp_path / "home")
    handle = store.create(context, manager, [])

    with pytest.raises(SessionBusyError):
        store.resume(handle.info.session_id)


def test_expired_lease_can_be_reclaimed(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    clock = [datetime(2026, 8, 4, tzinfo=UTC)]
    context, manager = make_runtime(project)
    store = SessionStore(project, home=tmp_path / "home", now=lambda: clock[0])
    handle = store.create(context, manager, [])
    clock[0] += timedelta(hours=2)

    resumed = store.resume(handle.info.session_id)

    assert resumed.info.session_id == handle.info.session_id


def test_partial_final_line_is_ignored_and_index_is_repaired(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    context, manager = make_runtime(project)
    store = SessionStore(project, home=tmp_path / "home")
    handle = store.create(context, manager, [])
    manager.conversation.append_user("safe")
    handle.commit_state()
    handle.close()
    log_path = store.sessions_dir / f"{handle.info.session_id}.jsonl"
    with log_path.open("ab") as stream:
        stream.write(b'{"seq":999')
    with store._connect() as connection:
        connection.execute(
            "UPDATE sessions SET last_seq = 0, last_hash = 'stale' WHERE session_id = ?",
            (handle.info.session_id,),
        )

    resumed = store.resume(handle.info.session_id)

    assert resumed.manager.conversation.active_items()[0]["content"] == "safe"
    assert resumed.info.last_seq == 2


def test_middle_corruption_marks_session_damaged(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    context, manager = make_runtime(project)
    store = SessionStore(project, home=tmp_path / "home")
    handle = store.create(context, manager, [])
    manager.conversation.append_user("safe")
    handle.commit_state()
    handle.close()
    log_path = store.sessions_dir / f"{handle.info.session_id}.jsonl"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    record: dict[str, Any] = json.loads(lines[1])
    record["todos"] = [{"content": "tampered", "status": "pending"}]
    lines[1] = json.dumps(record)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(SessionCorruptError):
        store.resume(handle.info.session_id)

    damaged = store.get_session(handle.info.session_id)
    assert damaged.status == "damaged"
    assert damaged.damaged is True


def test_soft_deleted_session_is_hidden_but_evidence_remains(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    context, manager = make_runtime(project)
    store = SessionStore(project, home=tmp_path / "home")
    handle = store.create(context, manager, [])
    handle.close()

    deleted = store.soft_delete(handle.info.session_id)

    assert deleted.status == "deleted"
    assert store.list_sessions() == []
    assert (store.sessions_dir / f"{handle.info.session_id}.jsonl").is_file()


def test_retry_save_recovers_record_flushed_before_index_update(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    context, manager = make_runtime(project)
    store = SessionStore(project, home=tmp_path / "home")
    handle = store.create(context, manager, [])
    manager.conversation.append_user("durable after retry")
    original_append = store._append

    def fail_after_log(current: Any, payload: dict[str, Any]) -> Any:
        with store._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (current.info.session_id,),
            ).fetchone()
        record = _make_record(
            row["last_seq"] + 1,
            row["last_hash"],
            _iso(store._now()),
            payload,
        )
        _append_line(Path(row["log_path"]), record)
        raise OSError("database update failed")

    monkeypatch.setattr(store, "_append", fail_after_log)
    with pytest.raises(OSError):
        handle.commit_state()
    assert handle.dirty is True
    monkeypatch.setattr(store, "_append", original_append)

    handle.retry_save()
    handle.close()
    resumed = store.resume(handle.info.session_id)

    assert resumed.manager.conversation.active_items()[0]["content"] == (
        "durable after retry"
    )
    assert resumed.info.last_seq == 2


def test_retry_save_discards_partial_tail_before_appending(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    context, manager = make_runtime(project)
    store = SessionStore(project, home=tmp_path / "home")
    handle = store.create(context, manager, [])
    manager.conversation.append_user("safe retry")
    log_path = store.sessions_dir / f"{handle.info.session_id}.jsonl"
    with log_path.open("ab") as stream:
        stream.write(b'{"partial":')
    handle.dirty = True

    handle.retry_save()
    handle.close()
    resumed = store.resume(handle.info.session_id)

    assert resumed.manager.conversation.active_items()[0]["content"] == "safe retry"


def test_startup_repairs_orphaned_log_and_stale_index(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    context, manager = make_runtime(project)
    home = tmp_path / "home"
    store = SessionStore(project, home=home)
    handle = store.create(context, manager, [])
    manager.conversation.append_user("recover the index")
    handle.commit_state()
    handle.close()
    session_id = handle.info.session_id
    with store._connect() as connection:
        connection.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    repaired_store = SessionStore(project, home=home)
    repaired = repaired_store.get_session(session_id)

    assert repaired.title == "recover the index"
    assert repaired.status == "closed"
    assert repaired.last_seq == 2
