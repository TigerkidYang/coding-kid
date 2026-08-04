from __future__ import annotations

import locale
import os
from pathlib import Path
import shlex
import sys
import time

import pytest

from coding_kid.terminal import (
    COMMAND_OUTPUT_MAX_BYTES,
    TIMEOUT_EXIT_CODE,
    _HeadTailBytes,
    _decode_process_output,
    _normalize_powershell_stderr,
    run_command,
)


def test_run_command_round_trips_unicode_and_separates_streams() -> None:
    result = run_command(
        f'{sys.executable} -c "import sys; print(chr(0x2733)); '
        'print(chr(0x4E2D), file=sys.stderr)"'
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "✳"
    assert result.stderr.strip() == "中"


def test_run_command_is_non_interactive() -> None:
    result = run_command(
        f"{sys.executable} -c \"import sys; print('eof' if "
        "sys.stdin.read() == '' else 'data')\""
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "eof"


def test_run_command_timeout_returns_partial_output() -> None:
    result = run_command(
        f"{sys.executable} -c \"import time; print('started', flush=True); "
        'time.sleep(5)"',
        timeout_seconds=0.1,
    )

    assert result.exit_code == TIMEOUT_EXIT_CODE
    assert result.timed_out
    assert "started" in result.stdout


def test_run_command_bounds_output_during_capture() -> None:
    result = run_command(
        f'{sys.executable} -c "import sys; '
        f"sys.stdout.write('a' * {COMMAND_OUTPUT_MAX_BYTES + 250_000} + 'tail')\""
    )

    assert result.exit_code == 0
    assert len(result.stdout.encode()) < COMMAND_OUTPUT_MAX_BYTES + 100
    assert "output bytes omitted" in result.stdout
    assert result.stdout.endswith("tail")


def test_timeout_terminates_descendant_processes(tmp_path: Path) -> None:
    marker = tmp_path / "descendant-finished"
    child = tmp_path / "child.py"
    child.write_text(
        "import pathlib, time\n"
        "time.sleep(0.6)\n"
        f"pathlib.Path({str(marker)!r}).write_text('alive', encoding='utf-8')\n",
        encoding="utf-8",
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, {str(child)!r}])\n"
        "print('parent started', flush=True)\n"
        "time.sleep(5)\n",
        encoding="utf-8",
    )

    command = (
        f'& "{sys.executable}" "{parent}"'
        if os.name == "nt"
        else f"{shlex.quote(sys.executable)} {shlex.quote(str(parent))}"
    )
    result = run_command(command, timeout_seconds=0.15)
    time.sleep(0.8)

    assert result.timed_out
    assert "parent started" in result.stdout
    assert not marker.exists()


def test_head_tail_capture_is_bounded_before_model_formatting() -> None:
    output = _HeadTailBytes(COMMAND_OUTPUT_MAX_BYTES)
    output.append(b"a" * COMMAND_OUTPUT_MAX_BYTES)
    output.append(b"middle" * COMMAND_OUTPUT_MAX_BYTES)
    output.append(b"z" * 100)

    rendered = output.render()

    assert len(rendered) < COMMAND_OUTPUT_MAX_BYTES + 100
    assert rendered.startswith(b"a")
    assert rendered.endswith(b"z" * 100)
    assert b"output bytes omitted" in rendered


def test_decode_prefers_utf8_then_legacy_encoding(monkeypatch) -> None:
    monkeypatch.setattr(locale, "getpreferredencoding", lambda _setlocale=False: "gbk")

    assert _decode_process_output("✳".encode()) == "✳"
    assert _decode_process_output("中文".encode("gbk")) == "中文"
    assert "�" in _decode_process_output(b"\x81")


def test_powershell_clixml_normalization_discards_progress_and_keeps_errors() -> None:
    progress = (
        '#< CLIXML\r\n<Objs xmlns="http://schemas.microsoft.com/powershell/2004/04">'
        '<Obj S="progress"><S S="Error">failure_x000D__x000A_</S></Obj>'
        "</Objs>"
    )

    assert _normalize_powershell_stderr(progress) == "failure"
    assert _normalize_powershell_stderr("plain error") == "plain error"


@pytest.mark.skipif(os.name != "nt", reason="PowerShell boundary is Windows-only")
def test_powershell_error_is_normalized_and_unicode_safe() -> None:
    result = run_command("Write-Error 'bad ✳'")

    assert result.exit_code == 1
    assert "bad ✳" in result.stderr
    assert "CLIXML" not in result.stderr
