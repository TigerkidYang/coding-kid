from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from coding_kid.sandbox import (
    DEFAULT_SANDBOX_IMAGE,
    SandboxConfig,
    SandboxError,
    SandboxMode,
    SandboxRuntime,
    SandboxViolation,
)


def runtime(
    project: Path,
    mode: SandboxMode = SandboxMode.WORKSPACE_WRITE,
    **kwargs: Any,
) -> SandboxRuntime:
    return SandboxRuntime(
        SandboxConfig(mode, project, project, **kwargs),
        docker_executable="docker",
        id_factory=lambda: "abcdef123456",
    )


def test_config_requires_cwd_inside_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()

    with pytest.raises(ValueError, match="inside"):
        SandboxConfig(SandboxMode.WORKSPACE_WRITE, project, outside)


def test_restricted_paths_stay_inside_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    sandbox = runtime(project)

    assert sandbox.resolve_path("new/file.txt", write=True) == (
        project / "new" / "file.txt"
    )
    with pytest.raises(SandboxViolation, match="outside project"):
        sandbox.resolve_path("../secret.txt")
    with pytest.raises(SandboxViolation, match="metadata"):
        sandbox.resolve_path(".git/config", write=True)
    with pytest.raises(SandboxViolation, match="metadata"):
        sandbox.resolve_path(".CODING-KID/skills/x", write=True)


def test_path_resolution_blocks_symlink_escape(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    try:
        (project / "link").symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    with pytest.raises(SandboxViolation, match="outside project"):
        runtime(project).resolve_path("link/secret.txt", write=True)


def test_read_only_blocks_writes_but_allows_project_reads(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    sandbox = runtime(project, SandboxMode.READ_ONLY)

    assert sandbox.resolve_path("README.md") == project / "README.md"
    with pytest.raises(SandboxViolation, match="read-only"):
        sandbox.resolve_path("README.md", write=True)


def test_danger_full_access_preserves_unrestricted_paths(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    sandbox = runtime(project, SandboxMode.DANGER_FULL_ACCESS)

    assert sandbox.resolve_path("../secret.txt") == project / "../secret.txt"
    assert "Backend: host" in sandbox.status_text()


def test_docker_command_is_hardened_and_does_not_include_host_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-leak")
    sandbox = runtime(project)

    argv = sandbox.command_argv("python -V", sandbox.new_container_name())
    rendered = "\n".join(argv)

    assert argv[:2] == ["docker", "run"]
    assert "--cap-drop" in argv
    assert "no-new-privileges" in argv
    assert "--read-only" in argv
    assert argv[argv.index("--network") + 1] == "none"
    assert f"{project}:/workspace:rw" in argv
    assert f"{project / '.git'}:/workspace/.git:ro" in argv
    assert "/workspace/.coding-kid:ro,size=64k" in argv
    assert "must-not-leak" not in rendered
    assert argv[-4:] == [DEFAULT_SANDBOX_IMAGE, "/bin/sh", "-lc", "python -V"]


def test_read_only_mount_and_explicit_network(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    sandbox = runtime(
        project,
        SandboxMode.READ_ONLY,
        network_enabled=True,
        image="custom/image:test",
    )

    argv = sandbox.command_argv("true", "coding-kid-abcdef")

    assert f"{project}:/workspace:ro" in argv
    assert argv[argv.index("--network") + 1] == "bridge"
    assert argv[-4] == "custom/image:test"


def test_availability_checks_daemon_and_image(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    calls: list[list[str]] = []

    def runner(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "ok", "")

    sandbox = SandboxRuntime(
        SandboxConfig(SandboxMode.WORKSPACE_WRITE, project, project),
        docker_executable="docker",
        runner=runner,
    )

    sandbox.check_available()

    assert calls[0][1:3] == ["version", "--format"]
    assert calls[1][1:3] == ["image", "inspect"]


def test_availability_fails_closed(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    def runner(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "daemon stopped")

    sandbox = SandboxRuntime(
        SandboxConfig(SandboxMode.WORKSPACE_WRITE, project, project),
        docker_executable="docker",
        runner=runner,
    )

    with pytest.raises(SandboxError, match="daemon stopped"):
        sandbox.check_available()


def test_remove_container_is_idempotent(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    calls: list[list[str]] = []

    def runner(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, "", "missing")

    sandbox = SandboxRuntime(
        SandboxConfig(SandboxMode.WORKSPACE_WRITE, project, project),
        docker_executable="docker",
        runner=runner,
    )

    sandbox.remove_container("coding-kid-abc")

    assert calls == [["docker", "rm", "-f", "coding-kid-abc"]]


def test_termination_cleanup_retries_container_creation_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    calls: list[list[str]] = []

    def runner(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0 if len(calls) == 3 else 1, "", "")

    monkeypatch.setattr("coding_kid.sandbox.time.sleep", lambda _: None)
    sandbox = SandboxRuntime(
        SandboxConfig(SandboxMode.WORKSPACE_WRITE, project, project),
        docker_executable="docker",
        runner=runner,
    )

    sandbox.remove_container("coding-kid-race", retry_missing=True)

    assert calls == [["docker", "rm", "-f", "coding-kid-race"]] * 3
