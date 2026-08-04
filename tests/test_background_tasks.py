from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from coding_kid.background_tasks import (
    BackgroundTaskError,
    BackgroundTaskManager,
    MAX_RUNNING_TASKS,
    TASK_OUTPUT_MAX_BYTES,
)
from coding_kid.events import CancellationToken, TurnCancelled


def _script_command(path: Path) -> str:
    return f'& "{sys.executable}" "{path}"'


def _write_script(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")


def test_background_task_captures_unicode_and_failure(tmp_path: Path) -> None:
    script = tmp_path / "worker.py"
    _write_script(
        script,
        "import sys\n"
        "print('你好 ✳', flush=True)\n"
        "print('错误 🐯', file=sys.stderr, flush=True)\n"
        "raise SystemExit(7)\n",
    )
    manager = BackgroundTaskManager(id_factory=lambda: "task_fixed")
    try:
        started = manager.start(_script_command(script))
        result, timed_out = manager.wait(started.task_id, 10)
    finally:
        manager.close()

    assert started.status == "running"
    assert result.status == "failed"
    assert result.exit_code == 7
    assert "你好 ✳" in result.stdout
    assert "错误 🐯" in result.stderr
    assert timed_out is False


def test_wait_timeout_and_cancellation_leave_task_running(tmp_path: Path) -> None:
    script = tmp_path / "slow.py"
    _write_script(script, "import time\ntime.sleep(30)\n")
    manager = BackgroundTaskManager()
    try:
        task_id = manager.start(_script_command(script)).task_id
        snapshot, timed_out = manager.wait(task_id, 0.01)
        assert timed_out is True
        assert snapshot.status == "running"

        token = CancellationToken()
        token.cancel()
        with pytest.raises(TurnCancelled):
            manager.wait(task_id, 1, token)
        assert manager.poll(task_id).status == "running"
    finally:
        manager.close()


def test_stop_is_idempotent_and_close_is_idempotent(tmp_path: Path) -> None:
    script = tmp_path / "slow.py"
    _write_script(script, "import time\ntime.sleep(30)\n")
    manager = BackgroundTaskManager()
    task_id = manager.start(_script_command(script)).task_id

    stopped = manager.stop(task_id)
    again = manager.stop(task_id)
    manager.close()
    manager.close()

    assert stopped.status == "stopped"
    assert again.status == "stopped"


def test_output_and_running_task_count_are_bounded(tmp_path: Path) -> None:
    noisy = tmp_path / "noisy.py"
    _write_script(noisy, f"print('x' * {TASK_OUTPUT_MAX_BYTES + 1000})\n")
    manager = BackgroundTaskManager()
    try:
        task_id = manager.start(_script_command(noisy)).task_id
        result, _ = manager.wait(task_id, 10)
        assert result.stdout_truncated is True
        assert "earlier output bytes omitted" in result.stdout

        slow = tmp_path / "slow.py"
        _write_script(slow, "import time\ntime.sleep(30)\n")
        for _ in range(MAX_RUNNING_TASKS):
            manager.start(_script_command(slow))
        with pytest.raises(BackgroundTaskError, match="At most"):
            manager.start(_script_command(slow))
    finally:
        manager.close()


def test_events_summary_and_unknown_id(tmp_path: Path) -> None:
    script = tmp_path / "done.py"
    _write_script(script, "print('done')\n")
    manager = BackgroundTaskManager(id_factory=lambda: "task_known")
    try:
        task_id = manager.start(_script_command(script)).task_id
        manager.wait(task_id, 10)
        events = manager.drain_events()

        assert [event.status for event in events] == ["running", "completed"]
        assert task_id in manager.prompt_summary()
        assert task_id in manager.status_text()
        assert manager.drain_events() == ()
        with pytest.raises(BackgroundTaskError, match="Unknown or expired"):
            manager.poll("missing")
    finally:
        manager.close()


def test_spawn_failure_does_not_register_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = BackgroundTaskManager()

    def fail_spawn(
        command: str, *, process_job: bool = False
    ) -> subprocess.Popen[bytes]:
        raise OSError("spawn failed")

    monkeypatch.setattr("coding_kid.background_tasks.spawn_command", fail_spawn)
    with pytest.raises(OSError, match="spawn failed"):
        manager.start("broken")

    assert manager.list() == ()
    assert manager.drain_events() == ()
    manager.close()


def test_oldest_terminal_record_is_evicted(tmp_path: Path) -> None:
    script = tmp_path / "done.py"
    _write_script(script, "pass\n")
    ids = iter(f"task_{index:02}" for index in range(33))
    manager = BackgroundTaskManager(id_factory=lambda: next(ids))
    try:
        for _ in range(33):
            task_id = manager.start(_script_command(script)).task_id
            manager.wait(task_id, 10)

        assert len(manager.list()) == 32
        with pytest.raises(BackgroundTaskError, match="Unknown or expired"):
            manager.poll("task_00")
        assert manager.poll("task_32").status == "completed"
    finally:
        manager.close()


def test_stop_terminates_descendant_processes(tmp_path: Path) -> None:
    marker = tmp_path / "descendant-finished.txt"
    child = tmp_path / "child.py"
    parent = tmp_path / "parent.py"
    spawned = tmp_path / "spawned.txt"
    _write_script(
        child,
        "import pathlib, time\n"
        "time.sleep(3)\n"
        f"pathlib.Path({str(marker)!r}).write_text('alive')\n",
    )
    _write_script(
        parent,
        "import pathlib, subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, {str(child)!r}])\n"
        f"pathlib.Path({str(spawned)!r}).write_text('ready')\n"
        "time.sleep(30)\n",
    )
    manager = BackgroundTaskManager()
    try:
        task_id = manager.start(_script_command(parent)).task_id
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not spawned.exists():
            time.sleep(0.02)
        assert spawned.exists()
        assert manager.stop(task_id).status == "stopped"
        time.sleep(3.2)
        assert not marker.exists()
    finally:
        manager.close()


def test_background_launch_returns_without_waiting_for_completion(
    tmp_path: Path,
) -> None:
    script = tmp_path / "slow.py"
    _write_script(script, "import time\ntime.sleep(2)\n")
    manager = BackgroundTaskManager()
    started_at = time.monotonic()
    try:
        manager.start(_script_command(script))
        assert time.monotonic() - started_at < 1
    finally:
        manager.close()


@pytest.mark.parametrize("round_number", range(10))
def test_concurrent_lifecycle_stress_has_no_regression_or_leak(
    tmp_path: Path,
    round_number: int,
) -> None:
    quick = tmp_path / f"quick-{round_number}.py"
    slow = tmp_path / f"slow-{round_number}.py"
    _write_script(quick, "import time\ntime.sleep(0.05)\n")
    _write_script(slow, "import time\ntime.sleep(30)\n")
    manager = BackgroundTaskManager()
    quick_ids = [manager.start(_script_command(quick)).task_id for _ in range(2)]
    slow_ids = [manager.start(_script_command(slow)).task_id for _ in range(2)]
    observed: dict[str, list[str]] = {task_id: [] for task_id in slow_ids}

    def observe_and_stop(task_id: str) -> None:
        observed[task_id].append(manager.poll(task_id).status)
        observed[task_id].append(manager.stop(task_id).status)
        observed[task_id].append(manager.poll(task_id).status)

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(manager.wait, task_id, 10) for task_id in quick_ids]
        futures.extend(pool.submit(observe_and_stop, task_id) for task_id in slow_ids)
        futures.append(pool.submit(manager.close))
        for future in futures:
            future.result(timeout=15)

    manager.close()
    snapshots = manager.list()
    assert all(snapshot.status != "running" for snapshot in snapshots)
    assert all(states[-1] == "stopped" for states in observed.values())
    task_prefixes = tuple(f"coding-kid-{item.task_id}" for item in snapshots)
    lingering = [
        thread.name
        for thread in threading.enumerate()
        if thread.name.startswith(task_prefixes)
    ]
    assert lingering == [], [(item.task_id, item.status) for item in snapshots]
    events = manager.drain_events()
    for snapshot in snapshots:
        statuses = [
            event.status for event in events if event.task_id == snapshot.task_id
        ]
        assert statuses[0] == "running"
        assert len(statuses) == 2
        assert statuses[-1] == snapshot.status
