"""Protected, content-addressed change checkpoints for one implementation stage."""

from __future__ import annotations

from dataclasses import dataclass
import difflib
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from threading import RLock
from typing import Any, Callable


MAX_CHECKPOINT_BYTES = 100 * 1024 * 1024
MAX_CHECKPOINT_FILES = 10_000
MAX_DIFF_CHARS = 30_000


class CheckpointError(RuntimeError):
    """Raised when the application cannot promise a safe rollback."""


class RollbackConflict(CheckpointError):
    def __init__(self, paths: list[str]) -> None:
        self.paths = tuple(paths)
        super().__init__(
            "Rollback refused because files changed outside the last recorded "
            f"Agent effect: {', '.join(paths)}"
        )


@dataclass(frozen=True)
class FileState:
    kind: str
    digest: str
    size: int

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "digest": self.digest, "size": self.size}

    @classmethod
    def from_dict(cls, value: object) -> FileState:
        if not isinstance(value, dict):
            raise CheckpointError("Invalid checkpoint file record")
        return cls(str(value["kind"]), str(value["digest"]), int(value["size"]))


@dataclass(frozen=True)
class ChangeSummary:
    modified: tuple[str, ...]
    deleted: tuple[str, ...]
    created: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not (self.modified or self.deleted or self.created)

    def text(self) -> str:
        lines = [
            f"Modified: {len(self.modified)}",
            f"Deleted: {len(self.deleted)}",
            f"Created: {len(self.created)}",
        ]
        for label, paths in (
            ("M", self.modified),
            ("D", self.deleted),
            ("A", self.created),
        ):
            lines.extend(f"{label} {path}" for path in paths)
        return "\n".join(lines)


class CheckpointManager:
    """Own baseline bytes and the last state produced by application effects."""

    def __init__(
        self,
        project_root: Path,
        state_root: Path,
        *,
        max_bytes: int = MAX_CHECKPOINT_BYTES,
        max_files: int = MAX_CHECKPOINT_FILES,
        running_tasks: Callable[[], int] | None = None,
        running_agents: Callable[[], int] | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.state_root = state_root.resolve()
        self.max_bytes = max_bytes
        self.max_files = max_files
        self._running_tasks = running_tasks or (lambda: 0)
        self._running_agents = running_agents or (lambda: 0)
        self._lock = RLock()

    def create(self) -> str:
        """Capture tracked and non-ignored untracked content before mutation."""
        with self._lock:
            paths = self._listed_paths()
            if len(paths) > self.max_files:
                raise CheckpointError(
                    f"Checkpoint has {len(paths)} files; limit is {self.max_files}"
                )
            checkpoint_id = f"checkpoint_{secrets.token_hex(8)}"
            directory = self.state_root / checkpoint_id
            blobs = directory / "blobs"
            blobs.mkdir(parents=True, exist_ok=False)
            try:
                baseline = self._capture(paths, blobs, save_blobs=True)
                total = sum(item.size for item in baseline.values())
                if total > self.max_bytes:
                    raise CheckpointError(
                        f"Checkpoint is {total} bytes; limit is {self.max_bytes}"
                    )
                self._write_manifest(directory, baseline, baseline)
            except BaseException:
                shutil.rmtree(directory, ignore_errors=True)
                raise
            return checkpoint_id

    def prepare_effect(self, checkpoint_id: str) -> None:
        """Refuse to begin when external changes appeared since our last record."""
        with self._lock:
            _, observed = self._load_manifest(checkpoint_id)
            current = self._capture(self._listed_paths(), None, save_blobs=False)
            conflicts = _state_differences(observed, current)
            if conflicts:
                raise RollbackConflict(conflicts)

    def record_effect(self, checkpoint_id: str) -> ChangeSummary:
        """Record the exact post-effect tree used for later conflict detection."""
        with self._lock:
            baseline, _ = self._load_manifest(checkpoint_id)
            current = self._capture(self._listed_paths(), None, save_blobs=False)
            self._write_manifest(self._directory(checkpoint_id), baseline, current)
            return _changes(baseline, current)

    def changes(self, checkpoint_id: str) -> ChangeSummary:
        with self._lock:
            baseline, observed = self._load_manifest(checkpoint_id)
            return _changes(baseline, observed)

    def refresh_read_only(self, checkpoint_id: str) -> ChangeSummary:
        """Report changes without claiming externally changed bytes as Agent output."""
        with self._lock:
            baseline, observed = self._load_manifest(checkpoint_id)
            current = self._capture(self._listed_paths(), None, save_blobs=False)
            conflicts = _state_differences(observed, current)
            if conflicts:
                raise RollbackConflict(conflicts)
            return _changes(baseline, observed)

    def rollback(self, checkpoint_id: str) -> ChangeSummary:
        with self._lock:
            if self._running_tasks():
                raise CheckpointError("Stop all background tasks before rollback")
            if self._running_agents():
                raise CheckpointError("Stop all child Agents before rollback")
            baseline, observed = self._load_manifest(checkpoint_id)
            current = self._capture(self._listed_paths(), None, save_blobs=False)
            conflicts = _state_differences(observed, current)
            if conflicts:
                raise RollbackConflict(conflicts)

            directory = self._directory(checkpoint_id)
            for relative in sorted(set(observed) - set(baseline), reverse=True):
                target = self._target(relative)
                if target.is_symlink() or target.is_file():
                    target.unlink()
            for relative, state in baseline.items():
                target = self._target(relative)
                if target.is_symlink() or target.is_file():
                    target.unlink()
                target.parent.mkdir(parents=True, exist_ok=True)
                content = (directory / "blobs" / state.digest).read_bytes()
                if state.kind == "symlink":
                    os.symlink(os.fsdecode(content), target)
                elif state.kind == "file":
                    target.write_bytes(content)
                else:
                    raise CheckpointError(f"Unsupported checkpoint type: {state.kind}")
            self._write_manifest(directory, baseline, baseline)
            return _changes(baseline, observed)

    def accept(self, checkpoint_id: str) -> ChangeSummary:
        with self._lock:
            changes = self.changes(checkpoint_id)
            shutil.rmtree(self._directory(checkpoint_id))
            return changes

    def diff_text(self, checkpoint_id: str) -> str:
        with self._lock:
            baseline, observed = self._load_manifest(checkpoint_id)
            directory = self._directory(checkpoint_id)
            chunks: list[str] = []
            for relative in sorted(set(baseline) | set(observed)):
                before = baseline.get(relative)
                after = observed.get(relative)
                if before == after:
                    continue
                old = self._text_blob(directory, before)
                new = self._text_current(relative, after)
                if old is None or new is None:
                    chunks.append(f"Binary/type change: {relative}\n")
                    continue
                chunks.extend(
                    difflib.unified_diff(
                        old.splitlines(keepends=True),
                        new.splitlines(keepends=True),
                        fromfile=f"a/{relative}",
                        tofile=f"b/{relative}",
                    )
                )
                if sum(len(item) for item in chunks) >= MAX_DIFF_CHARS:
                    chunks.append("\n... diff truncated ...\n")
                    break
            text = "".join(chunks) or "No stage changes."
            return text[: MAX_DIFF_CHARS + 30]

    def exists(self, checkpoint_id: str) -> bool:
        return (self._directory(checkpoint_id) / "manifest.json").is_file()

    def _listed_paths(self) -> list[str]:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(self.project_root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise CheckpointError(f"Cannot enumerate rollback files: {detail}")
        return sorted(os.fsdecode(item) for item in result.stdout.split(b"\0") if item)

    def _capture(
        self, paths: list[str], blobs: Path | None, *, save_blobs: bool
    ) -> dict[str, FileState]:
        captured: dict[str, FileState] = {}
        total = 0
        for relative in paths:
            target = self._target(relative)
            try:
                if target.is_symlink():
                    data = os.fsencode(os.readlink(target))
                    kind = "symlink"
                elif target.is_file():
                    data = target.read_bytes()
                    kind = "file"
                elif not target.exists():
                    continue
                else:
                    raise CheckpointError(f"Unsupported project entry: {relative}")
            except OSError as error:
                raise CheckpointError(
                    f"Cannot safely read {relative}: {error}"
                ) from error
            total += len(data)
            if total > self.max_bytes:
                raise CheckpointError(
                    f"Checkpoint exceeds {self.max_bytes} bytes while reading {relative}"
                )
            digest = hashlib.sha256(data).hexdigest()
            captured[relative] = FileState(kind, digest, len(data))
            if save_blobs:
                assert blobs is not None
                blob = blobs / digest
                if not blob.exists():
                    blob.write_bytes(data)
        return captured

    def _target(self, relative: str) -> Path:
        target = Path(os.path.abspath(self.project_root / relative))
        try:
            target.relative_to(self.project_root)
        except ValueError as error:
            raise CheckpointError(
                f"Checkpoint path escapes project: {relative}"
            ) from error
        return target

    def _directory(self, checkpoint_id: str) -> Path:
        if not checkpoint_id.startswith("checkpoint_") or any(
            character not in "0123456789abcdef"
            for character in checkpoint_id.removeprefix("checkpoint_")
        ):
            raise CheckpointError("Invalid checkpoint ID")
        directory = (self.state_root / checkpoint_id).resolve()
        try:
            directory.relative_to(self.state_root)
        except ValueError as error:
            raise CheckpointError("Checkpoint path escapes protected state") from error
        return directory

    def _write_manifest(
        self,
        directory: Path,
        baseline: dict[str, FileState],
        observed: dict[str, FileState],
    ) -> None:
        payload = {
            "version": 1,
            "project_root": str(self.project_root),
            "baseline": {key: value.to_dict() for key, value in baseline.items()},
            "observed": {key: value.to_dict() for key, value in observed.items()},
        }
        temporary = directory / "manifest.json.tmp"
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        temporary.replace(directory / "manifest.json")

    def _load_manifest(
        self, checkpoint_id: str
    ) -> tuple[dict[str, FileState], dict[str, FileState]]:
        directory = self._directory(checkpoint_id)
        try:
            payload = json.loads(
                (directory / "manifest.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            raise CheckpointError(
                f"Cannot load checkpoint {checkpoint_id}: {error}"
            ) from error
        if payload.get("version") != 1 or payload.get("project_root") != str(
            self.project_root
        ):
            raise CheckpointError("Checkpoint does not belong to this project")
        baseline = {
            key: FileState.from_dict(value)
            for key, value in payload.get("baseline", {}).items()
        }
        observed = {
            key: FileState.from_dict(value)
            for key, value in payload.get("observed", {}).items()
        }
        return baseline, observed

    def _text_blob(self, directory: Path, state: FileState | None) -> str | None:
        if state is None:
            return ""
        if state.kind != "file":
            return None
        try:
            return (directory / "blobs" / state.digest).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def _text_current(self, relative: str, state: FileState | None) -> str | None:
        if state is None:
            return ""
        if state.kind != "file":
            return None
        try:
            return self._target(relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None


def _state_differences(
    expected: dict[str, FileState], actual: dict[str, FileState]
) -> list[str]:
    return sorted(
        relative
        for relative in set(expected) | set(actual)
        if expected.get(relative) != actual.get(relative)
    )


def _changes(
    baseline: dict[str, FileState], current: dict[str, FileState]
) -> ChangeSummary:
    shared = set(baseline) & set(current)
    return ChangeSummary(
        tuple(sorted(path for path in shared if baseline[path] != current[path])),
        tuple(sorted(set(baseline) - set(current))),
        tuple(sorted(set(current) - set(baseline))),
    )
