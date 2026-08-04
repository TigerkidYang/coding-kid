"""Bounded process-local background shell task management."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import secrets
import subprocess
import threading
import time
from typing import Callable, Literal

from coding_kid.events import CancellationToken
from coding_kid.terminal import (
    IO_DRAIN_TIMEOUT_SECONDS,
    decode_process_output,
    normalize_process_stderr,
    spawn_command,
    terminate_process_tree,
)

MAX_RUNNING_TASKS = 8
MAX_RETAINED_TASKS = 32
TASK_OUTPUT_MAX_BYTES = 256_000
MAX_TASK_EVENTS = 64
MAX_WAIT_SECONDS = 30.0
_READ_CHUNK_BYTES = 8192
_WAIT_SLICE_SECONDS = 0.05

TaskStatus = Literal["running", "completed", "failed", "stopped"]
IdFactory = Callable[[], str]
Clock = Callable[[], float]


class BackgroundTaskError(RuntimeError):
    """Raised when a task operation cannot be completed."""


@dataclass(frozen=True)
class TaskEvent:
    task_id: str
    status: TaskStatus
    command: str
    exit_code: int | None = None


@dataclass(frozen=True)
class TaskSnapshot:
    task_id: str
    status: TaskStatus
    command: str
    exit_code: int | None
    duration_seconds: float
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool

    def model_text(self, *, wait_timed_out: bool = False) -> str:
        return (
            f"task_id: {self.task_id}\n"
            f"status: {self.status}\n"
            f"exit_code: {self.exit_code if self.exit_code is not None else 'null'}\n"
            f"wait_timed_out: {str(wait_timed_out).lower()}\n"
            f"duration_seconds: {self.duration_seconds:.3f}\n"
            f"stdout_truncated: {str(self.stdout_truncated).lower()}\n"
            f"stderr_truncated: {str(self.stderr_truncated).lower()}\n"
            f"stdout:\n{self.stdout.rstrip()}\n"
            f"stderr:\n{self.stderr.rstrip()}"
        )


class _TailBytes:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.data = bytearray()
        self.omitted = 0

    def append(self, chunk: bytes) -> None:
        self.data.extend(chunk)
        overflow = len(self.data) - self.limit
        if overflow > 0:
            del self.data[:overflow]
            self.omitted += overflow

    def render(self) -> bytes:
        if not self.omitted:
            return bytes(self.data)
        marker = f"... {self.omitted} earlier output bytes omitted ...\n".encode()
        return marker + bytes(self.data)


@dataclass
class _TaskRecord:
    task_id: str
    command: str
    process: subprocess.Popen[bytes]
    started_at: float
    status: TaskStatus = "running"
    exit_code: int | None = None
    ended_at: float | None = None
    stop_requested: bool = False
    stdout: _TailBytes = field(
        default_factory=lambda: _TailBytes(TASK_OUTPUT_MAX_BYTES)
    )
    stderr: _TailBytes = field(
        default_factory=lambda: _TailBytes(TASK_OUTPUT_MAX_BYTES)
    )
    condition: threading.Condition = field(
        default_factory=lambda: threading.Condition(threading.RLock())
    )
    readers: tuple[threading.Thread, ...] = ()
    watcher: threading.Thread | None = None


class BackgroundTaskManager:
    """Own background processes for one Coding Kid application lifetime."""

    def __init__(
        self,
        *,
        id_factory: IdFactory | None = None,
        clock: Clock = time.monotonic,
    ) -> None:
        self._id_factory = id_factory or (lambda: f"task_{secrets.token_hex(6)}")
        self._clock = clock
        self._tasks: dict[str, _TaskRecord] = {}
        self._events: deque[TaskEvent] = deque(maxlen=MAX_TASK_EVENTS)
        self._lock = threading.RLock()
        self._closed = False

    def start(self, command: str) -> TaskSnapshot:
        if not command:
            raise ValueError("command must not be empty")
        with self._lock:
            if self._closed:
                raise BackgroundTaskError("Background task manager is closed")
            if self.running_count >= MAX_RUNNING_TASKS:
                raise BackgroundTaskError(
                    f"At most {MAX_RUNNING_TASKS} background tasks may run at once"
                )
            self._evict_terminal_tasks()
            task_id = self._new_task_id()
            process = spawn_command(command)
            record = _TaskRecord(task_id, command, process, self._clock())
            self._tasks[task_id] = record
            self._events.append(TaskEvent(task_id, "running", command))

        assert process.stdout is not None
        assert process.stderr is not None
        readers = (
            threading.Thread(
                target=self._read_stream,
                args=(record, process.stdout, record.stdout),
                daemon=True,
                name=f"coding-kid-{task_id}-stdout",
            ),
            threading.Thread(
                target=self._read_stream,
                args=(record, process.stderr, record.stderr),
                daemon=True,
                name=f"coding-kid-{task_id}-stderr",
            ),
        )
        watcher = threading.Thread(
            target=self._watch,
            args=(record,),
            daemon=True,
            name=f"coding-kid-{task_id}-watcher",
        )
        record.readers = readers
        record.watcher = watcher
        for reader in readers:
            reader.start()
        watcher.start()
        return self._snapshot(record)

    @property
    def running_count(self) -> int:
        with self._lock:
            return sum(task.status == "running" for task in self._tasks.values())

    def list(self) -> tuple[TaskSnapshot, ...]:
        with self._lock:
            records = tuple(self._tasks.values())
        return tuple(self._snapshot(record) for record in records)

    def poll(self, task_id: str) -> TaskSnapshot:
        return self._snapshot(self._get(task_id))

    def wait(
        self,
        task_id: str,
        timeout_seconds: float = 10.0,
        cancellation_token: CancellationToken | None = None,
    ) -> tuple[TaskSnapshot, bool]:
        if timeout_seconds < 0 or timeout_seconds > MAX_WAIT_SECONDS:
            raise ValueError(
                f"timeout_seconds must be between 0 and {MAX_WAIT_SECONDS:g}"
            )
        record = self._get(task_id)
        deadline = self._clock() + timeout_seconds
        with record.condition:
            while record.status == "running":
                if cancellation_token is not None:
                    cancellation_token.raise_if_cancelled()
                remaining = deadline - self._clock()
                if remaining <= 0:
                    break
                record.condition.wait(min(_WAIT_SLICE_SECONDS, remaining))
            timed_out = record.status == "running"
        return self._snapshot(record), timed_out

    def stop(self, task_id: str) -> TaskSnapshot:
        record = self._get(task_id)
        with record.condition:
            if record.status != "running":
                return self._snapshot(record)
            record.stop_requested = True
        terminate_process_tree(record.process)
        snapshot, _ = self.wait(task_id, IO_DRAIN_TIMEOUT_SECONDS + 1.0)
        if snapshot.status == "running":
            self._finish(record, record.process.poll(), forced_status="stopped")
        return self._snapshot(record)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            running = [
                task.task_id
                for task in self._tasks.values()
                if task.status == "running"
            ]
        for task_id in running:
            self.stop(task_id)
        with self._lock:
            records = tuple(self._tasks.values())
        for record in records:
            if record.watcher is not None:
                record.watcher.join(IO_DRAIN_TIMEOUT_SECONDS + 1.0)
            for reader in record.readers:
                reader.join(IO_DRAIN_TIMEOUT_SECONDS)

    def drain_events(self) -> tuple[TaskEvent, ...]:
        with self._lock:
            events = tuple(self._events)
            self._events.clear()
            return events

    def prompt_summary(self) -> str:
        snapshots = self.list()
        running = [item for item in snapshots if item.status == "running"]
        terminal = [item for item in snapshots if item.status != "running"][-4:]
        selected = [*running, *terminal]
        if not selected:
            return ""
        lines = [
            "Background shell tasks are process-local; old IDs from resumed "
            "sessions are invalid. Current tasks:"
        ]
        lines.extend(
            f"- {item.task_id}: {item.status}; {_bounded(item.command)}"
            for item in selected
        )
        lines.append("Use the task tool to inspect output, wait, or stop a task.")
        return "\n".join(lines)

    def status_text(self) -> str:
        snapshots = self.list()
        if not snapshots:
            return "No background tasks."
        return "\n".join(
            f"{item.task_id}  {item.status}  {_bounded(item.command)}"
            for item in snapshots
        )

    def _get(self, task_id: str) -> _TaskRecord:
        if not task_id:
            raise ValueError("task_id is required")
        with self._lock:
            record = self._tasks.get(task_id)
        if record is None:
            raise BackgroundTaskError(f"Unknown or expired background task: {task_id}")
        return record

    def _new_task_id(self) -> str:
        for _ in range(100):
            task_id = self._id_factory()
            if task_id and task_id not in self._tasks:
                return task_id
        raise BackgroundTaskError("Could not allocate a unique background task ID")

    def _evict_terminal_tasks(self) -> None:
        while len(self._tasks) >= MAX_RETAINED_TASKS:
            terminal_id = next(
                (
                    task_id
                    for task_id, task in self._tasks.items()
                    if task.status != "running"
                ),
                None,
            )
            if terminal_id is None:
                raise BackgroundTaskError("Background task record limit reached")
            del self._tasks[terminal_id]

    def _read_stream(
        self,
        record: _TaskRecord,
        stream: object,
        output: _TailBytes,
    ) -> None:
        try:
            while chunk := stream.read(_READ_CHUNK_BYTES):  # type: ignore[attr-defined]
                with record.condition:
                    output.append(chunk)
                    record.condition.notify_all()
        except (OSError, ValueError):
            pass

    def _watch(self, record: _TaskRecord) -> None:
        exit_code = record.process.wait()
        deadline = self._clock() + IO_DRAIN_TIMEOUT_SECONDS
        for reader in record.readers:
            reader.join(max(0.0, deadline - self._clock()))
        self._finish(record, exit_code)

    def _finish(
        self,
        record: _TaskRecord,
        exit_code: int | None,
        *,
        forced_status: TaskStatus | None = None,
    ) -> None:
        with record.condition:
            if record.status != "running":
                return
            record.exit_code = exit_code
            record.ended_at = self._clock()
            record.status = forced_status or (
                "stopped"
                if record.stop_requested
                else "completed"
                if exit_code == 0
                else "failed"
            )
            record.condition.notify_all()
        with self._lock:
            self._events.append(
                TaskEvent(record.task_id, record.status, record.command, exit_code)
            )

    def _snapshot(self, record: _TaskRecord) -> TaskSnapshot:
        with record.condition:
            ended_at = record.ended_at or self._clock()
            stdout = record.stdout.render()
            stderr = record.stderr.render()
            return TaskSnapshot(
                record.task_id,
                record.status,
                record.command,
                record.exit_code,
                max(0.0, ended_at - record.started_at),
                decode_process_output(stdout),
                normalize_process_stderr(decode_process_output(stderr)),
                bool(record.stdout.omitted),
                bool(record.stderr.omitted),
            )


def _bounded(value: str, limit: int = 120) -> str:
    rendered = " ".join(value.splitlines())
    return rendered if len(rendered) <= limit else f"{rendered[: limit - 3]}..."
