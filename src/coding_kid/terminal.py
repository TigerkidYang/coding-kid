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

COMMAND_TIMEOUT_SECONDS = 120.0
COMMAND_OUTPUT_MAX_BYTES = 1_000_000
IO_DRAIN_TIMEOUT_SECONDS = 2.0
TIMEOUT_EXIT_CODE = 124


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

    def model_text(self) -> str:
        return (
            f"exit_code: {self.exit_code}\n"
            f"timed_out: {str(self.timed_out).lower()}\n"
            f"duration_seconds: {self.duration_seconds:.3f}\n"
            f"stdout:\n{self.stdout.rstrip()}\n"
            f"stderr:\n{self.stderr.rstrip()}"
        )


def run_command(
    command: str,
    *,
    timeout_seconds: float = COMMAND_TIMEOUT_SECONDS,
) -> CommandResult:
    """Run a non-interactive command with bounded byte capture and cleanup."""
    if not command:
        raise ValueError("command must not be empty")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    started = time.monotonic()
    process = spawn_command(command)
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
    try:
        try:
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_tree(process)
            exit_code = TIMEOUT_EXIT_CODE
    except BaseException:
        _terminate_process_tree(process)
        raise
    finally:
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
    )


def spawn_command(command: str) -> subprocess.Popen[bytes]:
    """Start one non-interactive command using the shared terminal boundary."""
    if not command:
        raise ValueError("command must not be empty")
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    process_options: dict[str, object] = {}
    if os.name == "nt":
        process_options["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )
    else:
        process_options["start_new_session"] = True
    return subprocess.Popen(
        _shell_argv(command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        **process_options,
    )


def decode_process_output(data: bytes) -> str:
    """Decode command bytes through the shared Unicode fallback policy."""
    return _decode_process_output(data)


def normalize_process_stderr(stderr: str) -> str:
    """Normalize redirected PowerShell stderr on Windows."""
    return _normalize_powershell_stderr(stderr) if os.name == "nt" else stderr


def terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Terminate a command and its descendants with bounded cleanup."""
    _terminate_process_tree(process)


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
    if process.poll() is not None:
        return
    if os.name == "nt":
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
    else:
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
