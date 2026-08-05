"""Bounded process-local execution-session management."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Callable, Literal

from coding_kid.events import CancellationToken
from coding_kid.sandbox import SandboxRuntime
from coding_kid.terminal import (
    IO_DRAIN_TIMEOUT_SECONDS,
    CommandResult,
    InteractiveProcess,
    decode_process_output,
    normalize_process_stderr,
    normalize_terminal_output,
    release_process_tree,
    run_command,
    spawn_command,
    spawn_interactive_command,
    terminate_process_tree,
)

MAX_RUNNING_TASKS = 8
MAX_RETAINED_TASKS = 32
TASK_OUTPUT_MAX_BYTES = 256_000
MAX_TASK_EVENTS = 64
MAX_WAIT_SECONDS = 30.0
MAX_WRITE_CHARS = 20_000
_READ_CHUNK_BYTES = 8192
_WAIT_SLICE_SECONDS = 0.05
_INPUT_RESPONSE_WAIT_SECONDS = 1.0

TaskStatus = Literal["running", "completed", "failed", "interrupted", "stopped"]
IdFactory = Callable[[], str]
Clock = Callable[[], float]
ManagedProcess = subprocess.Popen[bytes] | InteractiveProcess


class BackgroundTaskError(RuntimeError):
    """Raised when an execution-session operation cannot be completed."""


@dataclass(frozen=True)
class TaskEvent:
    task_id: str
    status: TaskStatus
    command: str
    exit_code: int | None = None
    interactive: bool = False


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
    interactive: bool = False
    stdout_log: str | None = None
    stderr_log: str | None = None
    incremental: bool = False

    def model_text(self, *, wait_timed_out: bool = False) -> str:
        return (
            f"task_id: {self.task_id}\n"
            f"status: {self.status}\n"
            f"interactive: {str(self.interactive).lower()}\n"
            f"exit_code: {self.exit_code if self.exit_code is not None else 'null'}\n"
            f"wait_timed_out: {str(wait_timed_out).lower()}\n"
            f"incremental: {str(self.incremental).lower()}\n"
            f"duration_seconds: {self.duration_seconds:.3f}\n"
            f"stdout_truncated: {str(self.stdout_truncated).lower()}\n"
            f"stderr_truncated: {str(self.stderr_truncated).lower()}\n"
            f"stdout_log: {self.stdout_log or 'null'}\n"
            f"stderr_log: {self.stderr_log or 'null'}\n"
            f"stdout:\n{self.stdout.rstrip()}\n"
            f"stderr:\n{self.stderr.rstrip()}"
        )


class _OutputBytes:
    """Keep useful head/tail evidence and an incremental absolute cursor."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._head_limit = limit // 2
        self._tail_limit = limit - self._head_limit
        self.head = bytearray()
        self.tail = bytearray()
        self.recent = bytearray()
        self.total = 0

    @property
    def omitted(self) -> int:
        return self.total - len(self.head) - len(self.tail)

    def append(self, chunk: bytes) -> None:
        self.total += len(chunk)
        self.recent.extend(chunk)
        recent_overflow = len(self.recent) - self.limit
        if recent_overflow > 0:
            del self.recent[:recent_overflow]
        head_remaining = self._head_limit - len(self.head)
        if head_remaining > 0:
            self.head.extend(chunk[:head_remaining])
            chunk = chunk[head_remaining:]
        if not chunk:
            return
        self.tail.extend(chunk)
        overflow = len(self.tail) - self._tail_limit
        if overflow > 0:
            del self.tail[:overflow]

    def render(self) -> bytes:
        if not self.omitted:
            return bytes(self.head + self.tail)
        marker = f"... {self.omitted} earlier output bytes omitted ...\n".encode()
        return bytes(self.head) + b"\n" + marker + bytes(self.tail)

    def since(self, cursor: int) -> tuple[bytes, int, bool]:
        if cursor == 0:
            return self.render(), self.total, bool(self.omitted)
        recent_start = self.total - len(self.recent)
        lost = cursor < recent_start
        available_cursor = max(cursor, recent_start)
        offset = max(0, available_cursor - recent_start)
        output = bytes(self.recent[offset:])
        if lost:
            marker = f"... {recent_start - cursor} unread output bytes omitted ...\n".encode()
            output = marker + output
        return output, self.total, lost


@dataclass
class _TaskRecord:
    task_id: str
    command: str
    process: ManagedProcess
    started_at: float
    interactive: bool = False
    status: TaskStatus = "running"
    exit_code: int | None = None
    ended_at: float | None = None
    stop_requested: bool = False
    interrupt_requested: bool = False
    stdout: _OutputBytes = field(
        default_factory=lambda: _OutputBytes(TASK_OUTPUT_MAX_BYTES)
    )
    stderr: _OutputBytes = field(
        default_factory=lambda: _OutputBytes(TASK_OUTPUT_MAX_BYTES)
    )
    stdout_cursor: int = 0
    stderr_cursor: int = 0
    stdout_log: Path | None = None
    stderr_log: Path | None = None
    condition: threading.Condition = field(
        default_factory=lambda: threading.Condition(threading.RLock())
    )
    termination_lock: threading.Lock = field(default_factory=threading.Lock)
    readers: tuple[threading.Thread, ...] = ()
    watcher: threading.Thread | None = None


class BackgroundTaskManager:
    """Own every continuing command for one Coding Kid process lifetime."""

    def __init__(
        self,
        *,
        id_factory: IdFactory | None = None,
        clock: Clock = time.monotonic,
        sandbox_runtime: SandboxRuntime | None = None,
    ) -> None:
        self._id_factory = id_factory or (lambda: f"task_{secrets.token_hex(6)}")
        self._clock = clock
        self.sandbox_runtime = sandbox_runtime
        self._tasks: dict[str, _TaskRecord] = {}
        self._events: deque[TaskEvent] = deque(maxlen=MAX_TASK_EVENTS)
        self._lock = threading.RLock()
        self._closed = False
        self._close_complete = threading.Event()
        self._log_root = Path(tempfile.mkdtemp(prefix="coding-kid-exec-"))

    def start(self, command: str, *, interactive: bool = False) -> TaskSnapshot:
        if not command:
            raise ValueError("command must not be empty")
        with self._lock:
            if self._closed:
                raise BackgroundTaskError("Execution-session manager is closed")
            if self.running_count >= MAX_RUNNING_TASKS:
                raise BackgroundTaskError(
                    f"At most {MAX_RUNNING_TASKS} execution sessions may run at once"
                )
            self._evict_terminal_tasks()
            task_id = self._new_task_id()
            if interactive:
                process = spawn_interactive_command(
                    command, sandbox_runtime=self.sandbox_runtime
                )
            else:
                spawn_options: dict[str, object] = {"process_job": True}
                if self.sandbox_runtime is not None:
                    spawn_options["sandbox_runtime"] = self.sandbox_runtime
                process = spawn_command(command, **spawn_options)
            record = _TaskRecord(
                task_id,
                command,
                process,
                self._clock(),
                interactive=interactive,
                stdout_log=self._log_root / f"{task_id}.stdout.log",
                stderr_log=self._log_root / f"{task_id}.stderr.log",
            )
            record.stdout_log.touch()
            record.stderr_log.touch()
            self._tasks[task_id] = record
            self._events.append(
                TaskEvent(task_id, "running", command, interactive=interactive)
            )
            if interactive:
                readers = (
                    threading.Thread(
                        target=self._read_interactive,
                        args=(record,),
                        daemon=True,
                        name=f"coding-kid-{task_id}-terminal",
                    ),
                )
            else:
                assert isinstance(process, subprocess.Popen)
                assert process.stdout is not None
                assert process.stderr is not None
                readers = (
                    threading.Thread(
                        target=self._read_stream,
                        args=(record, process.stdout, record.stdout, record.stdout_log),
                        daemon=True,
                        name=f"coding-kid-{task_id}-stdout",
                    ),
                    threading.Thread(
                        target=self._read_stream,
                        args=(record, process.stderr, record.stderr, record.stderr_log),
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

    def poll(self, task_id: str, *, incremental: bool = False) -> TaskSnapshot:
        record = self._get(task_id)
        return self._consume(record) if incremental else self._snapshot(record)

    def settle(self, task_id: str, timeout_seconds: float = 0.25) -> TaskSnapshot:
        """Briefly drain evidence at a turn-interruption boundary."""
        record = self._get(task_id)
        deadline = self._clock() + max(0.0, timeout_seconds)
        with record.condition:
            before = record.stdout.total + record.stderr.total
            while (
                record.status == "running"
                and record.stdout.total + record.stderr.total == before
            ):
                remaining = deadline - self._clock()
                if remaining <= 0:
                    break
                record.condition.wait(min(_WAIT_SLICE_SECONDS, remaining))
        return self._consume(record)

    def wait(
        self,
        task_id: str,
        timeout_seconds: float = 10.0,
        cancellation_token: CancellationToken | None = None,
        *,
        incremental: bool = False,
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
        snapshot = self._consume(record) if incremental else self._snapshot(record)
        return snapshot, timed_out

    def write(self, task_id: str, value: str, *, submit: bool = True) -> TaskSnapshot:
        if not isinstance(value, str):
            raise ValueError("input must be a string")
        if len(value) > MAX_WRITE_CHARS:
            raise ValueError(f"input may contain at most {MAX_WRITE_CHARS} characters")
        record = self._get(task_id)
        with record.condition:
            if record.status != "running":
                raise BackgroundTaskError(f"Execution session is {record.status}")
            if not record.interactive:
                raise BackgroundTaskError(
                    "Input is available only for interactive execution sessions"
                )
            before = record.stdout.total
            # A later accepted input proves Ctrl+C did not terminate the
            # session; any eventual exit belongs to the continued interaction.
            record.interrupt_requested = False
            ending = "\r\n" if os.name == "nt" else "\n"
            record.process.write(value + (ending if submit else ""))  # type: ignore[union-attr]
            self._wait_for_output(record, before)
        return self._consume(record)

    def interrupt(self, task_id: str) -> TaskSnapshot:
        record = self._get(task_id)
        with record.condition:
            if record.status != "running":
                return self._snapshot(record)
            if not record.interactive:
                raise BackgroundTaskError(
                    "Interrupt is available only for interactive execution sessions"
                )
            before = record.stdout.total
            record.interrupt_requested = True
            record.process.interrupt()  # type: ignore[union-attr]
            self._wait_for_output(record, before)
        return self._consume(record)

    def check(
        self,
        task_id: str,
        command: str,
        timeout_seconds: float = 10.0,
        cancellation_token: CancellationToken | None = None,
    ) -> CommandResult:
        if not command:
            raise ValueError("check command must not be empty")
        if timeout_seconds <= 0 or timeout_seconds > MAX_WAIT_SECONDS:
            raise ValueError(
                f"timeout_seconds must be between 0 and {MAX_WAIT_SECONDS:g}"
            )
        record = self._get(task_id)
        with record.condition:
            if record.status != "running":
                raise BackgroundTaskError(
                    f"Cannot check a session that is {record.status}"
                )
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()
        runtime = self.sandbox_runtime
        if runtime is None or not runtime.restricted:
            return run_command(
                command,
                timeout_seconds=timeout_seconds,
                cancellation_token=cancellation_token,
            )
        container_name = getattr(record.process, "_coding_kid_container", None)
        if not container_name:
            raise BackgroundTaskError("Execution container is no longer available")
        started = self._clock()
        argv = runtime.check_argv(container_name, command)
        deadline = started + timeout_seconds
        while True:
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()
            remaining = deadline - self._clock()
            if remaining <= 0:
                return CommandResult(
                    124,
                    "",
                    "Execution container did not become available before timeout.",
                    True,
                    self._clock() - started,
                )
            try:
                completed = subprocess.run(
                    argv,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=remaining,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                return CommandResult(
                    124,
                    decode_process_output(error.stdout or b""),
                    decode_process_output(error.stderr or b""),
                    True,
                    self._clock() - started,
                )
            stderr = decode_process_output(completed.stderr)
            if (
                completed.returncode != 0
                and "No such container" in stderr
                and record.process.poll() is None
            ):
                time.sleep(min(0.1, max(0.0, deadline - self._clock())))
                continue
            return CommandResult(
                completed.returncode,
                decode_process_output(completed.stdout),
                stderr,
                False,
                self._clock() - started,
            )

    def stop(self, task_id: str) -> TaskSnapshot:
        record = self._get(task_id)
        with record.termination_lock:
            with record.condition:
                if record.status != "running":
                    return self._snapshot(record)
                record.stop_requested = True
            terminate_process_tree(record.process)
            snapshot, _ = self.wait(task_id, IO_DRAIN_TIMEOUT_SECONDS + 1.0)
            if snapshot.status == "running":
                self._finish(record, record.process.poll(), forced_status="stopped")
            self._join_record_threads(record)
            return self._snapshot(record)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                close_complete = self._close_complete
                owns_close = False
            else:
                self._closed = True
                close_complete = self._close_complete
                owns_close = True
                running = [
                    task.task_id
                    for task in self._tasks.values()
                    if task.status == "running"
                ]
        if not owns_close:
            close_complete.wait()
            return
        try:
            for task_id in running:
                self.stop(task_id)
            with self._lock:
                records = tuple(self._tasks.values())
            for record in records:
                if record.process.poll() is None:
                    terminate_process_tree(record.process)
            for record in records:
                self._join_record_threads(record)
        finally:
            shutil.rmtree(self._log_root, ignore_errors=True)
            close_complete.set()

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
            "Execution sessions are process-local; old IDs from resumed sessions "
            "are invalid. Current sessions:"
        ]
        lines.extend(
            f"- {item.task_id}: {item.status}; interactive={item.interactive}; "
            f"{_bounded(item.command)}"
            for item in selected
        )
        lines.append(
            "Use task to poll incremental output, wait, write to an interactive "
            "terminal, interrupt it, check service readiness, or stop it. A "
            "running process is not proof that a service is ready."
        )
        return "\n".join(lines)

    def status_text(self) -> str:
        snapshots = self.list()
        if not snapshots:
            return "No execution sessions."
        return "\n".join(
            f"{item.task_id}  {item.status}  "
            f"{'interactive' if item.interactive else 'non-interactive'}  "
            f"{_bounded(item.command)}"
            for item in snapshots
        )

    def _get(self, task_id: str) -> _TaskRecord:
        if not task_id:
            raise ValueError("task_id is required")
        with self._lock:
            record = self._tasks.get(task_id)
        if record is None:
            raise BackgroundTaskError(
                f"Unknown or expired execution session: {task_id}"
            )
        return record

    def _new_task_id(self) -> str:
        for _ in range(100):
            task_id = self._id_factory()
            if task_id and task_id not in self._tasks:
                return task_id
        raise BackgroundTaskError("Could not allocate a unique execution-session ID")

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
                raise BackgroundTaskError("Execution-session record limit reached")
            record = self._tasks.pop(terminal_id)
            for path in (record.stdout_log, record.stderr_log):
                if path is not None:
                    path.unlink(missing_ok=True)

    def _read_stream(
        self,
        record: _TaskRecord,
        stream: object,
        output: _OutputBytes,
        log_path: Path | None,
    ) -> None:
        log = log_path.open("ab") if log_path is not None else None
        try:
            while chunk := stream.read(_READ_CHUNK_BYTES):  # type: ignore[attr-defined]
                if log is not None:
                    log.write(chunk)
                    log.flush()
                with record.condition:
                    output.append(chunk)
                    record.condition.notify_all()
        except (OSError, ValueError):
            pass
        finally:
            if log is not None:
                log.close()

    def _read_interactive(self, record: _TaskRecord) -> None:
        assert record.stdout_log is not None
        with record.stdout_log.open("ab") as log:
            try:
                while chunk := record.process.read(_READ_CHUNK_BYTES):  # type: ignore[union-attr]
                    log.write(chunk)
                    log.flush()
                    with record.condition:
                        record.stdout.append(chunk)
                        record.condition.notify_all()
            except (EOFError, OSError, ValueError):
                pass

    def _watch(self, record: _TaskRecord) -> None:
        exit_code = record.process.wait()
        release_process_tree(record.process)
        deadline = self._clock() + IO_DRAIN_TIMEOUT_SECONDS
        for reader in record.readers:
            reader.join(max(0.0, deadline - self._clock()))
        self._finish(record, exit_code)

    def _join_record_threads(self, record: _TaskRecord) -> None:
        if record.watcher is not None:
            record.watcher.join(IO_DRAIN_TIMEOUT_SECONDS + 1.0)
        alive_readers = [reader for reader in record.readers if reader.is_alive()]
        if alive_readers and isinstance(record.process, subprocess.Popen):
            for stream in (record.process.stdout, record.process.stderr):
                if stream is None:
                    continue
                try:
                    os.close(stream.fileno())
                except (OSError, ValueError):
                    pass
        for reader in alive_readers:
            reader.join(IO_DRAIN_TIMEOUT_SECONDS)

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
                else "interrupted"
                if record.interrupt_requested and exit_code not in {0, None}
                else "completed"
                if exit_code == 0
                else "failed"
            )
            record.condition.notify_all()
        with self._lock:
            self._events.append(
                TaskEvent(
                    record.task_id,
                    record.status,
                    record.command,
                    exit_code,
                    record.interactive,
                )
            )

    def _wait_for_output(self, record: _TaskRecord, previous_total: int) -> None:
        deadline = self._clock() + _INPUT_RESPONSE_WAIT_SECONDS
        while record.status == "running" and record.stdout.total == previous_total:
            remaining = deadline - self._clock()
            if remaining <= 0:
                return
            record.condition.wait(min(_WAIT_SLICE_SECONDS, remaining))

    def _snapshot(self, record: _TaskRecord) -> TaskSnapshot:
        with record.condition:
            ended_at = record.ended_at or self._clock()
            stdout = record.stdout.render()
            stderr = record.stderr.render()
            stdout_text = decode_process_output(stdout)
            if record.interactive:
                stdout_text = normalize_terminal_output(stdout_text)
            return TaskSnapshot(
                record.task_id,
                record.status,
                record.command,
                record.exit_code,
                max(0.0, ended_at - record.started_at),
                stdout_text,
                normalize_process_stderr(decode_process_output(stderr)),
                bool(record.stdout.omitted),
                bool(record.stderr.omitted),
                record.interactive,
                str(record.stdout_log) if record.stdout_log else None,
                str(record.stderr_log) if record.stderr_log else None,
            )

    def _consume(self, record: _TaskRecord) -> TaskSnapshot:
        with record.condition:
            ended_at = record.ended_at or self._clock()
            stdout, record.stdout_cursor, stdout_lost = record.stdout.since(
                record.stdout_cursor
            )
            stderr, record.stderr_cursor, stderr_lost = record.stderr.since(
                record.stderr_cursor
            )
            stdout_text = decode_process_output(stdout)
            if record.interactive:
                stdout_text = normalize_terminal_output(stdout_text)
            return TaskSnapshot(
                record.task_id,
                record.status,
                record.command,
                record.exit_code,
                max(0.0, ended_at - record.started_at),
                stdout_text,
                normalize_process_stderr(decode_process_output(stderr)),
                stdout_lost,
                stderr_lost,
                record.interactive,
                str(record.stdout_log) if record.stdout_log else None,
                str(record.stderr_log) if record.stderr_log else None,
                True,
            )


def _bounded(value: str, limit: int = 120) -> str:
    rendered = " ".join(value.splitlines())
    return rendered if len(rendered) <= limit else f"{rendered[: limit - 3]}..."
