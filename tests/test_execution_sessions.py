from __future__ import annotations

import os
from pathlib import Path
import sys
import time

import pytest

from coding_kid.background_tasks import BackgroundTaskError, BackgroundTaskManager
from coding_kid.tools import build_tool_registry


def _python_command(arguments: str) -> str:
    executable = str(Path(sys.executable))
    return (
        f'& "{executable}" {arguments}'
        if os.name == "nt"
        else f'"{executable}" {arguments}'
    )


def _collect_until(
    manager: BackgroundTaskManager,
    task_id: str,
    needle: str,
    *,
    timeout: float = 8,
    initial: str = "",
) -> str:
    output = initial
    deadline = time.monotonic() + timeout
    while needle not in output and time.monotonic() < deadline:
        output += manager.poll(task_id, incremental=True).stdout
        if needle not in output:
            time.sleep(0.05)
    assert needle in output, repr(output)
    return output


def test_foreground_execute_yields_same_process_and_incremental_output() -> None:
    manager = BackgroundTaskManager(id_factory=lambda: "task_yielded")
    registry = build_tool_registry(manager)
    command = _python_command(
        "-u -c \"import time; print('first', flush=True); "
        "time.sleep(0.4); print('second', flush=True)\""
    )
    try:
        initial = registry.dispatch(
            "execute",
            {
                "command": command,
                "background": False,
                "interactive": False,
                "yield_time_ms": 100,
                "reason": None,
            },
        )
        assert "task_id: task_yielded" in initial
        assert "status: running" in initial

        completed = registry.dispatch(
            "task",
            {
                "action": "wait",
                "task_id": "task_yielded",
                "input": None,
                "submit": True,
                "command": None,
                "timeout_seconds": 5,
                "reason": None,
            },
        )
    finally:
        manager.close()

    assert "status: completed" in completed
    assert "second" in completed
    assert ("first" in initial) != ("first" in completed)


def test_noninteractive_session_rejects_input() -> None:
    manager = BackgroundTaskManager(id_factory=lambda: "task_pipe")
    try:
        task_id = manager.start(
            _python_command('-c "import time; time.sleep(5)"')
        ).task_id
        with pytest.raises(BackgroundTaskError, match="only for interactive"):
            manager.write(task_id, "hello")
        with pytest.raises(BackgroundTaskError, match="only for interactive"):
            manager.interrupt(task_id)
    finally:
        manager.close()


def test_interactive_python_repl_preserves_unicode_state_and_ctrl_c() -> None:
    manager = BackgroundTaskManager(id_factory=lambda: "task_repl")
    try:
        task_id = manager.start(_python_command("-i -u"), interactive=True).task_id
        _collect_until(manager, task_id, ">>>")

        output = manager.write(task_id, "value = '你好🐯'").stdout
        output += manager.write(task_id, "print(value)").stdout
        output = _collect_until(manager, task_id, "你好🐯", initial=output)
        assert "你好🐯" in output

        manager.write(task_id, "import time; time.sleep(30)")
        interrupted = manager.interrupt(task_id)
        assert interrupted.status == "running"
        _collect_until(manager, task_id, ">>>")

        output = manager.write(task_id, "print('still-usable')").stdout
        output = _collect_until(manager, task_id, "still-usable", initial=output)
        assert "still-usable" in output
        manager.write(task_id, "exit()")
        final, timed_out = manager.wait(task_id, 5)
        assert timed_out is False
        assert final.status in {"completed", "failed"}
    finally:
        manager.close()


def test_explicit_health_check_and_log_lifecycle() -> None:
    manager = BackgroundTaskManager(id_factory=lambda: "task_checked")
    task_id = manager.start(_python_command('-c "import time; time.sleep(5)"')).task_id
    snapshot = manager.poll(task_id)
    assert snapshot.stdout_log is not None
    log_path = Path(snapshot.stdout_log)
    assert log_path.exists()

    result = manager.check(
        task_id,
        _python_command("-c \"print('ready-evidence')\""),
        5,
    )
    assert result.exit_code == 0
    assert "ready-evidence" in result.stdout

    manager.close()
    assert not log_path.exists()


def test_unknown_id_reports_expired_session() -> None:
    manager = BackgroundTaskManager()
    try:
        with pytest.raises(BackgroundTaskError, match="expired execution session"):
            manager.poll("task_from_old_process")
    finally:
        manager.close()
