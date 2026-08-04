from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from coding_kid import launcher

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("v1", "v1"),
        ("V2", "v2"),
        ("3", "v3"),
        ("03", "v3"),
        (" v3 ", "v3"),
        ("v4", "v4"),
        ("05", "v5"),
        ("v6", "v6"),
        ("07", "v7"),
        ("8", "v8"),
        ("09", "v9"),
        ("v10", "v10"),
    ],
)
def test_normalize_version_accepts_documented_aliases(
    value: str, expected: str
) -> None:
    assert launcher.normalize_version(value) == expected


@pytest.mark.parametrize("value", ["", "latest", "v0", "v11", "one"])
def test_normalize_version_rejects_unknown_values(value: str) -> None:
    with pytest.raises(ValueError):
        launcher.normalize_version(value)


def test_main_defaults_to_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    selected: list[str] = []
    monkeypatch.setattr(
        launcher,
        "launch_version",
        lambda version, options: selected.append(version) or 0,
    )

    assert launcher.main([]) == 0
    assert selected == [launcher.LATEST_VERSION]


def test_main_selects_explicit_version(monkeypatch: pytest.MonkeyPatch) -> None:
    selected: list[str] = []
    monkeypatch.setattr(
        launcher,
        "launch_version",
        lambda version, options: selected.append(version) or 0,
    )

    assert launcher.main(["V02"]) == 0
    assert selected == ["v2"]


def test_main_passes_resume_selection_to_latest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected: list[tuple[str, launcher.cli.SessionOptions]] = []
    monkeypatch.setattr(
        launcher,
        "launch_version",
        lambda version, options: selected.append((version, options)) or 0,
    )

    assert launcher.main(["v10", "--resume", "abc123"]) == 0
    assert selected == [
        (
            "v10",
            launcher.cli.SessionOptions(mode="resume", session_id="abc123"),
        )
    ]


def test_main_rejects_session_options_for_historical_version() -> None:
    with pytest.raises(SystemExit, match="2"):
        launcher.main(["v5", "--continue"])


def test_main_lists_versions_without_launching(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        launcher,
        "launch_version",
        lambda version: pytest.fail(f"unexpected launch: {version}"),
    )

    assert launcher.main(["--list-versions"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "v1",
        "v2",
        "v3",
        "v4",
        "v5",
        "v6",
        "v7",
        "v8",
        "v9",
        "v10 (latest, default)",
    ]


def test_main_rejects_unknown_version_before_launch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        launcher,
        "launch_version",
        lambda version: pytest.fail(f"unexpected launch: {version}"),
    )

    with pytest.raises(SystemExit, match="2"):
        launcher.main(["v99"])

    assert (
        "available versions: v1, v2, v3, v4, v5, v6, v7, v8, v9, v10"
        in capsys.readouterr().err
    )


def test_latest_version_runs_in_process(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[bool] = []
    monkeypatch.setattr(launcher.cli, "main", lambda options=None: called.append(True))

    assert launcher.launch_version("v10") == 0
    assert called == [True]


def test_historical_version_runs_isolated_and_preserves_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], Path, dict[str, str]]] = []

    def fake_run(
        command: list[str], *, cwd: Path, env: dict[str, str], check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        calls.append((command, cwd, env))
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", "existing-path")
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    assert launcher.launch_version("v2") == 7
    command, cwd, environment = calls[0]
    assert command == [sys.executable, "-c", launcher.RUNTIME_ENTRYPOINT]
    assert cwd == tmp_path
    assert environment["PYTHONPATH"].split(os.pathsep) == [
        str(launcher.bundled_runtime_root("v2")),
        "existing-path",
    ]


@pytest.mark.parametrize(
    ("version", "archive"),
    [
        ("v01", "01-minimal-agent"),
        ("v02", "02-task-decomposition"),
        ("v03", "03-context-assembly"),
        ("v04", "04-context-management"),
        ("v05", "05-streaming-tui"),
        ("v06", "06-persistent-memory"),
        ("v07", "07-pluggable-capabilities"),
        ("v08", "08-background-tasks"),
        ("v09", "09-multi-agent-workflows"),
    ],
)
def test_bundled_runtime_matches_archive(version: str, archive: str) -> None:
    archived_root = ROOT / "versions" / archive / "src" / "coding_kid"
    bundled_root = ROOT / "src" / "coding_kid" / "_runtimes" / version / "coding_kid"
    excluded = (
        {"__main__.py", "launcher.py"}
        if version in {"v04", "v05", "v06", "v07", "v08", "v09"}
        else set()
    )
    archived_files = {
        path.name: path.read_bytes()
        for path in archived_root.glob("*.py")
        if path.name not in excluded
    }
    bundled_files = {path.name: path.read_bytes() for path in bundled_root.glob("*.py")}

    assert bundled_files == archived_files


@pytest.mark.parametrize(
    "version",
    [None, "v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9", "v10"],
)
def test_module_launcher_starts_from_unrelated_project(
    version: str | None, tmp_path: Path
) -> None:
    command = [sys.executable, "-m", "coding_kid"]
    if version is not None:
        command.append(version)
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in [str(ROOT / "src"), existing_pythonpath] if part
    )

    completed = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        input="/exit\n",
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Coding Kid is ready." in completed.stdout
    assert "Goodbye." in completed.stdout
