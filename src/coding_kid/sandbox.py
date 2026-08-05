"""Fail-closed sandbox policy for model-controlled local effects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from typing import Callable, Sequence

DEFAULT_SANDBOX_IMAGE = "python:3.11-slim-bookworm"
PROTECTED_WORKSPACE_NAMES = frozenset({".git", ".coding-kid"})
DOCKER_LABEL = "com.coding-kid.sandbox=true"


class SandboxMode(str, Enum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"


class SandboxError(RuntimeError):
    """Raised when the configured isolation backend cannot be used safely."""


class SandboxViolation(PermissionError):
    """Raised when a model-controlled operation exceeds its active policy."""


@dataclass(frozen=True)
class SandboxConfig:
    """One immutable process-wide sandbox selection."""

    mode: SandboxMode
    project_root: Path
    cwd: Path
    image: str = DEFAULT_SANDBOX_IMAGE
    network_enabled: bool = False

    def __post_init__(self) -> None:
        root = self.project_root.resolve()
        cwd = self.cwd.resolve()
        try:
            cwd.relative_to(root)
        except ValueError as error:
            raise ValueError("sandbox cwd must be inside the project root") from error
        if not self.image.strip():
            raise ValueError("sandbox image must not be empty")
        if self.mode is SandboxMode.DANGER_FULL_ACCESS and self.network_enabled:
            raise ValueError("--sandbox-network is redundant with danger-full-access")
        object.__setattr__(self, "project_root", root)
        object.__setattr__(self, "cwd", cwd)
        object.__setattr__(self, "image", self.image.strip())

    @property
    def restricted(self) -> bool:
        return self.mode is not SandboxMode.DANGER_FULL_ACCESS


Runner = Callable[..., subprocess.CompletedProcess[str]]


class SandboxRuntime:
    """Resolve paths and construct Docker commands under one policy."""

    def __init__(
        self,
        config: SandboxConfig,
        *,
        docker_executable: str | None = None,
        runner: Runner = subprocess.run,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.config = config
        self._docker = docker_executable
        self._runner = runner
        self._id_factory = id_factory or (lambda: secrets.token_hex(6))

    @property
    def restricted(self) -> bool:
        return self.config.restricted

    @property
    def docker_executable(self) -> str:
        if self._docker:
            return self._docker
        executable = shutil.which("docker")
        if executable is None:
            raise SandboxError(
                "Docker CLI was not found; install Docker or explicitly use "
                "--sandbox danger-full-access"
            )
        self._docker = executable
        return executable

    def check_available(self) -> None:
        """Verify the daemon and configured image without pulling or fallback."""
        if not self.restricted:
            return
        self._check(
            [self.docker_executable, "version", "--format", "{{.Server.Version}}"],
            "Docker daemon is unavailable",
        )
        self._check(
            [self.docker_executable, "image", "inspect", self.config.image],
            (
                f"Sandbox image is unavailable: {self.config.image}. "
                f"Pull it explicitly with: docker pull {self.config.image}"
            ),
        )

    def _check(self, command: Sequence[str], message: str) -> None:
        try:
            result = self._runner(
                list(command),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise SandboxError(f"{message}: {error}") from error
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            suffix = f": {detail}" if detail else ""
            raise SandboxError(f"{message}{suffix}")

    def resolve_path(self, path: str, *, write: bool = False) -> Path:
        """Resolve one tool path and enforce project and metadata boundaries."""
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.config.cwd / candidate
        if not self.restricted:
            return candidate

        resolved = candidate.resolve(strict=False)
        try:
            relative = resolved.relative_to(self.config.project_root)
        except ValueError as error:
            raise SandboxViolation(
                f"sandbox blocked path outside project: {path}"
            ) from error
        if write and self.config.mode is SandboxMode.READ_ONLY:
            raise SandboxViolation("sandbox is read-only")
        if write and relative.parts:
            first = relative.parts[0].casefold()
            if first in PROTECTED_WORKSPACE_NAMES:
                raise SandboxViolation(
                    f"sandbox protects workspace metadata: {relative.parts[0]}"
                )
        return resolved

    def new_container_name(self) -> str:
        suffix = self._id_factory()
        if not suffix or any(
            character not in "0123456789abcdef" for character in suffix
        ):
            raise SandboxError("sandbox container ID factory returned an invalid value")
        return f"coding-kid-{suffix}"

    def command_argv(self, command: str, container_name: str) -> list[str]:
        """Build one hardened, non-shell Docker invocation."""
        if not self.restricted:
            raise SandboxError("danger-full-access does not use Docker")
        relative_cwd = self.config.cwd.relative_to(self.config.project_root)
        container_cwd = Path("/workspace", relative_cwd).as_posix()
        mount_mode = "ro" if self.config.mode is SandboxMode.READ_ONLY else "rw"
        argv = [
            self.docker_executable,
            "run",
            "--rm",
            "--name",
            container_name,
            "--label",
            DOCKER_LABEL,
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--read-only",
            "--pids-limit",
            "256",
            "--memory",
            "1g",
            "--cpus",
            "2",
            "--user",
            _container_user(),
            "--network",
            "bridge" if self.config.network_enabled else "none",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=256m",
            "--volume",
            f"{self.config.project_root}:/workspace:{mount_mode}",
            "--workdir",
            container_cwd,
            "--env",
            "HOME=/tmp/coding-kid",
            "--env",
            "LANG=C.UTF-8",
            "--env",
            "PYTHONIOENCODING=utf-8",
            "--env",
            "PYTHONUTF8=1",
        ]
        if self.config.mode is SandboxMode.WORKSPACE_WRITE:
            for name in sorted(PROTECTED_WORKSPACE_NAMES):
                host_path = self.config.project_root / name
                target = f"/workspace/{name}"
                if host_path.exists():
                    argv.extend(["--volume", f"{host_path}:{target}:ro"])
                else:
                    argv.extend(["--tmpfs", f"{target}:ro,size=64k"])
        argv.extend([self.config.image, "/bin/sh", "-lc", command])
        return argv

    def remove_container(self, container_name: str) -> None:
        """Idempotently remove a command container and its process tree."""
        if not self.restricted:
            return
        try:
            self._runner(
                [self.docker_executable, "rm", "-f", container_name],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    def status_text(self) -> str:
        backend = "docker" if self.restricted else "host"
        network = (
            "host"
            if not self.restricted
            else "enabled"
            if self.config.network_enabled
            else "disabled"
        )
        image = self.config.image if self.restricted else "n/a"
        return (
            f"Sandbox: {self.config.mode.value}\n"
            f"Backend: {backend}\n"
            f"Project root: {self.config.project_root}\n"
            f"Network: {network}\n"
            f"Image: {image}"
        )

    def instruction_text(self) -> str:
        if not self.restricted:
            return (
                "Sandbox policy: danger-full-access. Local tools run directly on "
                "the host with its PowerShell environment."
            )
        access = (
            "read-only"
            if self.config.mode is SandboxMode.READ_ONLY
            else "writable except for .git and .coding-kid"
        )
        network = "enabled" if self.config.network_enabled else "disabled"
        return (
            "Sandbox policy:\n"
            f"- Mode: {self.config.mode.value}.\n"
            f"- Project /workspace is {access}.\n"
            "- execute runs POSIX /bin/sh inside a fresh Linux container; use "
            "project-relative paths.\n"
            f"- Container network is {network}.\n"
            "- Do not request host execution or attempt to change the policy."
        )


def _container_user() -> str:
    if os.name != "nt" and hasattr(os, "getuid") and hasattr(os, "getgid"):
        return f"{os.getuid()}:{os.getgid()}"
    return "1000:1000"
