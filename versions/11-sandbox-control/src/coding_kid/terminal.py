"""Bounded, Unicode-safe foreground command execution."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import locale
import os
import re
import subprocess
import threading
import time
import xml.etree.ElementTree as ElementTree

from coding_kid.events import CancellationToken, TurnCancelled
from coding_kid.sandbox import SandboxRuntime

COMMAND_TIMEOUT_SECONDS = 120.0
COMMAND_OUTPUT_MAX_BYTES = 1_000_000
IO_DRAIN_TIMEOUT_SECONDS = 2.0
TIMEOUT_EXIT_CODE = 124
CANCELLED_EXIT_CODE = 125
_CREATE_SUSPENDED = 0x00000004


class _HeadTailBytes:
    """Retain bounded output while preserving useful beginnings and endings."""

    def __init__(self, limit: int) -> None:
        self._head_limit = limit // 2
        self._tail_limit = limit - self._head_limit
        self._head = bytearray()
        self._tail = bytearray()
        self.omitted = 0

    def append(self, chunk: bytes) -> None:
        if not chunk:
            return
        head_remaining = self._head_limit - len(self._head)
        if head_remaining > 0:
            head_chunk = chunk[:head_remaining]
            self._head.extend(head_chunk)
            chunk = chunk[len(head_chunk) :]
        if not chunk:
            return

        combined = self._tail + chunk
        if len(combined) > self._tail_limit:
            dropped = len(combined) - self._tail_limit
            self.omitted += dropped
            del combined[:dropped]
        self._tail = combined

    def render(self) -> bytes:
        if not self.omitted:
            return bytes(self._head + self._tail)
        marker = f"\n... {self.omitted} output bytes omitted ...\n".encode()
        return bytes(self._head) + marker + bytes(self._tail)


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_seconds: float
    cancelled: bool = False

    def model_text(self) -> str:
        return (
            f"exit_code: {self.exit_code}\n"
            f"timed_out: {str(self.timed_out).lower()}\n"
            f"cancelled: {str(self.cancelled).lower()}\n"
            f"duration_seconds: {self.duration_seconds:.3f}\n"
            f"stdout:\n{self.stdout.rstrip()}\n"
            f"stderr:\n{self.stderr.rstrip()}"
        )


def run_command(
    command: str,
    *,
    timeout_seconds: float = COMMAND_TIMEOUT_SECONDS,
    cancellation_token: CancellationToken | None = None,
    sandbox_runtime: SandboxRuntime | None = None,
) -> CommandResult:
    """Run a non-interactive command with bounded byte capture and cleanup."""
    if not command:
        raise ValueError("command must not be empty")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    started = time.monotonic()
    process = spawn_command(
        command,
        process_job=True,
        sandbox_runtime=sandbox_runtime,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    stdout = _HeadTailBytes(COMMAND_OUTPUT_MAX_BYTES)
    stderr = _HeadTailBytes(COMMAND_OUTPUT_MAX_BYTES)
    readers = [
        threading.Thread(
            target=_read_stream,
            args=(process.stdout, stdout),
            daemon=True,
            name="coding-kid-stdout",
        ),
        threading.Thread(
            target=_read_stream,
            args=(process.stderr, stderr),
            daemon=True,
            name="coding-kid-stderr",
        ),
    ]
    for reader in readers:
        reader.start()

    timed_out = False
    cancelled = False
    try:
        try:
            if cancellation_token is None:
                exit_code = process.wait(timeout=timeout_seconds)
            else:
                deadline = time.monotonic() + timeout_seconds
                while True:
                    cancellation_token.raise_if_cancelled()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(command, timeout_seconds)
                    try:
                        exit_code = process.wait(timeout=min(0.05, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        continue
        except TurnCancelled:
            cancelled = True
            _terminate_process_tree(process)
            exit_code = CANCELLED_EXIT_CODE
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_tree(process)
            exit_code = TIMEOUT_EXIT_CODE
    except BaseException:
        _terminate_process_tree(process)
        raise
    finally:
        release_process_tree(process)
        _finish_readers(process, readers)

    stderr_text = _decode_process_output(stderr.render())
    if os.name == "nt":
        stderr_text = _normalize_powershell_stderr(stderr_text)
    return CommandResult(
        exit_code=exit_code,
        stdout=_decode_process_output(stdout.render()),
        stderr=stderr_text,
        timed_out=timed_out,
        duration_seconds=time.monotonic() - started,
        cancelled=cancelled,
    )


def spawn_command(
    command: str,
    *,
    process_job: bool = False,
    sandbox_runtime: SandboxRuntime | None = None,
) -> subprocess.Popen[bytes]:
    """Start one non-interactive command using the shared terminal boundary."""
    if not command:
        raise ValueError("command must not be empty")
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    process_options: dict[str, object] = {}
    if os.name == "nt":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )
        if process_job:
            creationflags |= _CREATE_SUSPENDED
        process_options["creationflags"] = creationflags
    else:
        process_options["start_new_session"] = True
    restricted = sandbox_runtime is not None and sandbox_runtime.restricted
    container_name = sandbox_runtime.new_container_name() if restricted else None
    command_argv = (
        sandbox_runtime.command_argv(command, container_name)
        if restricted and container_name is not None
        else _shell_argv(command)
    )
    process = subprocess.Popen(
        command_argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        **process_options,
    )
    if container_name is not None:
        setattr(process, "_coding_kid_sandbox_runtime", sandbox_runtime)
        setattr(process, "_coding_kid_container", container_name)
    if os.name == "nt" and process_job:
        try:
            _attach_windows_job(process)
            _resume_windows_process(process)
        except BaseException:
            process.kill()
            process.wait()
            _close_windows_job(process)
            raise
    return process


def decode_process_output(data: bytes) -> str:
    """Decode command bytes through the shared Unicode fallback policy."""
    return _decode_process_output(data)


def normalize_process_stderr(stderr: str) -> str:
    """Normalize redirected PowerShell stderr on Windows."""
    return _normalize_powershell_stderr(stderr) if os.name == "nt" else stderr


def terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Terminate a command and its descendants with bounded cleanup."""
    _terminate_process_tree(process)


def release_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Release process-group resources, killing any descendants still attached."""
    _cleanup_sandbox(process)
    if os.name == "nt":
        _close_windows_job(process)


def _shell_argv(command: str) -> list[str]:
    if os.name == "nt":
        # Windows PowerShell accepts UTF-16LE encoded scripts, avoiding both the
        # active ANSI code page and nested command-line quoting. Its output is
        # explicitly UTF-8, matching Codex's Windows shell boundary.
        script = (
            "try { "
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "$OutputEncoding = [Console]::OutputEncoding "
            "} catch {}\n"
            f"{command}\n"
            "$ckkSuccess = $?; $ckkExitCode = $LASTEXITCODE; "
            "if (-not $ckkSuccess) { "
            "if ($ckkExitCode) { exit $ckkExitCode }; exit 1 }; "
            "if ($ckkExitCode) { exit $ckkExitCode }"
        )
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        return [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-OutputFormat",
            "Text",
            "-EncodedCommand",
            encoded,
        ]
    shell = os.environ.get("SHELL") or "/bin/sh"
    return [shell, "-lc", command]


def _read_stream(stream: object, buffer: _HeadTailBytes) -> None:
    try:
        while chunk := stream.read(8192):  # type: ignore[attr-defined]
            buffer.append(chunk)
    except (OSError, ValueError):
        # The parent closes a stuck inherited pipe after the drain deadline.
        pass


def _finish_readers(
    process: subprocess.Popen[bytes], readers: list[threading.Thread]
) -> None:
    deadline = time.monotonic() + IO_DRAIN_TIMEOUT_SECONDS
    for reader in readers:
        reader.join(max(0.0, deadline - time.monotonic()))
    # A descendant may have inherited a pipe even though the direct process
    # exited. The daemon readers retain only bounded buffers; returning is safer
    # than closing a buffered stream from another thread, which can itself block.


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "nt":
            # Use both boundaries. taskkill sees descendants that may have started
            # just before Job assignment; the Job catches descendants created while
            # taskkill is enumerating the tree.
            if process.poll() is None:
                try:
                    subprocess.run(
                        ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                        timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                except (OSError, subprocess.SubprocessError):
                    pass
            _terminate_windows_job(process)
        else:
            if process.poll() is not None:
                return
            try:
                os.killpg(process.pid, 15)
            except OSError:
                pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=1)
            except (OSError, subprocess.SubprocessError):
                pass
    finally:
        # Stop the Docker client first. Otherwise an immediate cancellation can
        # race `docker rm` and create the named container after cleanup returns.
        _cleanup_sandbox(process, retry_missing=True)


def _attach_windows_job(process: subprocess.Popen[bytes]) -> None:
    """Place a new Windows process in a kill-on-close Job Object when possible."""
    import ctypes
    from ctypes import wintypes

    class IoCounters(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_ulonglong)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return
    info = ExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = 0x00002000
    configured = kernel32.SetInformationJobObject(
        job,
        9,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )
    assigned = configured and kernel32.AssignProcessToJobObject(
        job, wintypes.HANDLE(process._handle)
    )
    if not assigned:
        kernel32.CloseHandle(job)
        return
    setattr(process, "_coding_kid_job", job)


def _resume_windows_process(process: subprocess.Popen[bytes]) -> None:
    """Resume every initial thread after the process enters its Job Object."""
    import ctypes
    from ctypes import wintypes

    class ThreadEntry32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD),
            ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", wintypes.LONG),
            ("tpDeltaPri", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry32)]
    kernel32.Thread32First.restype = wintypes.BOOL
    kernel32.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry32)]
    kernel32.Thread32Next.restype = wintypes.BOOL
    kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenThread.restype = wintypes.HANDLE
    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.ResumeThread.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000004, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if not snapshot or snapshot == invalid_handle:
        raise OSError(ctypes.get_last_error(), "Could not enumerate process threads")
    resumed = False
    try:
        entry = ThreadEntry32(dwSize=ctypes.sizeof(ThreadEntry32))
        has_entry = bool(kernel32.Thread32First(snapshot, ctypes.byref(entry)))
        while has_entry:
            if entry.th32OwnerProcessID == process.pid:
                thread = kernel32.OpenThread(0x0002, False, entry.th32ThreadID)
                if thread:
                    try:
                        if kernel32.ResumeThread(thread) != 0xFFFFFFFF:
                            resumed = True
                    finally:
                        kernel32.CloseHandle(thread)
            has_entry = bool(kernel32.Thread32Next(snapshot, ctypes.byref(entry)))
    finally:
        kernel32.CloseHandle(snapshot)
    if not resumed:
        raise OSError(ctypes.get_last_error(), "Could not resume command process")


def _terminate_windows_job(process: subprocess.Popen[bytes]) -> bool:
    import ctypes
    from ctypes import wintypes

    job = getattr(process, "_coding_kid_job", None)
    if not job:
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    terminated = bool(kernel32.TerminateJobObject(wintypes.HANDLE(job), 1))
    _close_windows_job(process)
    return terminated


def _close_windows_job(process: subprocess.Popen[bytes]) -> None:
    import ctypes
    from ctypes import wintypes

    job = getattr(process, "_coding_kid_job", None)
    if not job:
        return
    setattr(process, "_coding_kid_job", None)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(wintypes.HANDLE(job))


def _cleanup_sandbox(
    process: subprocess.Popen[bytes], *, retry_missing: bool = False
) -> None:
    runtime = getattr(process, "_coding_kid_sandbox_runtime", None)
    container_name = getattr(process, "_coding_kid_container", None)
    if runtime is None or container_name is None:
        return
    setattr(process, "_coding_kid_sandbox_runtime", None)
    setattr(process, "_coding_kid_container", None)
    runtime.remove_container(container_name, retry_missing=retry_missing)


def _decode_process_output(data: bytes) -> str:
    """Prefer UTF-8, accept the platform legacy codec, then decode lossily."""
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        legacy = locale.getpreferredencoding(False)
        if legacy.lower().replace("-", "") not in {"utf8", "utf_8"}:
            try:
                return data.decode(legacy)
            except (LookupError, UnicodeDecodeError):
                pass
        return data.decode("utf-8", errors="replace")


_POWERSHELL_ESCAPE = re.compile(r"_x([0-9A-Fa-f]{4})_")


def _normalize_powershell_stderr(stderr: str) -> str:
    """Remove progress-only CLIXML while preserving real PowerShell errors."""
    marker = "#< CLIXML"
    if marker not in stderr:
        return stderr
    plain, _, xml_text = stderr.partition(marker)
    xml_text = xml_text.lstrip("\r\n")
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        if 'S="Error"' not in xml_text and "S='Error'" not in xml_text:
            return plain.rstrip()
        return stderr

    errors: list[str] = []
    for item in root.iter():
        if item.attrib.get("S") != "Error" or not item.text:
            continue
        decoded = _POWERSHELL_ESCAPE.sub(
            lambda match: chr(int(match.group(1), 16)), item.text
        )
        if decoded.strip():
            errors.append(decoded.rstrip())
    parts = [part.rstrip() for part in (plain, *errors) if part.rstrip()]
    return "\n".join(parts)
