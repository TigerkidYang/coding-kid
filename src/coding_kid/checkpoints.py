"""Protected, content-addressed change checkpoints for one implementation stage."""

from __future__ import annotations

from dataclasses import dataclass
import difflib
from enum import Enum
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
MAX_UNCOVERED_EFFECTS = 256


class CheckpointError(RuntimeError):
    """Raised when the application cannot promise a safe rollback."""


class RollbackConflict(CheckpointError):
    def __init__(self, paths: list[str]) -> None:
        self.paths = tuple(paths)
        super().__init__(
            "Rollback refused because files changed outside the last recorded "
            f"Agent effect: {', '.join(paths)}"
        )


class CheckpointPolicy(str, Enum):
    """Requested recovery guarantee for one implementation stage."""

    REQUIRED = "required"
    BEST_EFFORT = "best-effort"
    OFF = "off"


class RecoveryCoverage(str, Enum):
    """Actual local-filesystem coverage available for one stage."""

    FULL = "full"
    SCOPED = "scoped"
    NONE = "none"


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


@dataclass(frozen=True)
class CheckpointStatus:
    policy: CheckpointPolicy
    coverage: RecoveryCoverage
    degraded_reason: str | None
    scoped_paths: tuple[str, ...]
    uncovered_effects: tuple[str, ...]

    @property
    def partial(self) -> bool:
        return self.coverage is RecoveryCoverage.SCOPED and bool(
            self.uncovered_effects
        )


@dataclass(frozen=True)
class _Manifest:
    baseline: dict[str, FileState]
    observed: dict[str, FileState]
    status: CheckpointStatus


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

    def create(
        self, policy: CheckpointPolicy = CheckpointPolicy.REQUIRED
    ) -> str:
        """Start a stage with the strongest coverage allowed by ``policy``."""
        with self._lock:
            policy = CheckpointPolicy(policy)
            if policy is CheckpointPolicy.OFF:
                return self._create_empty_stage(
                    policy,
                    RecoveryCoverage.NONE,
                    "Application checkpointing was explicitly disabled.",
                )
            if policy is CheckpointPolicy.BEST_EFFORT and not self._is_git_project():
                return self._create_empty_stage(
                    policy,
                    RecoveryCoverage.SCOPED,
                    "Non-Git project: protecting only files targeted by built-in edits.",
                )
            try:
                return self._create_full_stage(policy)
            except CheckpointError as error:
                if policy is CheckpointPolicy.REQUIRED:
                    raise
                return self._create_empty_stage(
                    policy,
                    RecoveryCoverage.SCOPED,
                    f"Full checkpoint unavailable: {error}",
                )

    def _create_full_stage(self, policy: CheckpointPolicy) -> str:
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
            status = CheckpointStatus(
                policy, RecoveryCoverage.FULL, None, (), ()
            )
            self._write_manifest(
                directory, _Manifest(baseline, dict(baseline), status)
            )
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        return checkpoint_id

    def _create_empty_stage(
        self,
        policy: CheckpointPolicy,
        coverage: RecoveryCoverage,
        reason: str,
    ) -> str:
        checkpoint_id = f"checkpoint_{secrets.token_hex(8)}"
        directory = self.state_root / checkpoint_id
        (directory / "blobs").mkdir(parents=True, exist_ok=False)
        status = CheckpointStatus(policy, coverage, reason, (), ())
        self._write_manifest(directory, _Manifest({}, {}, status))
        return checkpoint_id

    def prepare_effect(
        self,
        checkpoint_id: str,
        *,
        paths: tuple[str, ...] | None = None,
        effect_label: str = "unknown",
    ) -> str | None:
        """Check conflicts and extend scoped recovery before one effect."""
        with self._lock:
            manifest = self._load_manifest(checkpoint_id)
            status = manifest.status
            if status.coverage is RecoveryCoverage.NONE:
                self._append_uncovered_effect(checkpoint_id, manifest, effect_label)
                return None
            if status.coverage is RecoveryCoverage.FULL:
                current = self._capture(self._listed_paths(), None, save_blobs=False)
                conflicts = _state_differences(manifest.observed, current)
                if conflicts:
                    raise RollbackConflict(conflicts)
                return None

            relative_paths = self._scoped_relative_paths(paths)
            if relative_paths is None:
                self._append_uncovered_effect(checkpoint_id, manifest, effect_label)
                return (
                    "Recovery coverage is partial: this effect has no predictable "
                    "project-file target."
                )
            scoped_paths = tuple(sorted(set(status.scoped_paths) | set(relative_paths)))
            current_before = self._capture(
                list(status.scoped_paths), None, save_blobs=False
            )
            conflicts = _state_differences(manifest.observed, current_before)
            if conflicts:
                raise RollbackConflict(conflicts)

            new_paths = sorted(set(scoped_paths) - set(status.scoped_paths))
            if len(scoped_paths) > self.max_files:
                raise CheckpointError(
                    f"Scoped recovery has {len(scoped_paths)} files; limit is "
                    f"{self.max_files}"
                )
            baseline = dict(manifest.baseline)
            observed = dict(manifest.observed)
            if new_paths:
                captured = self._capture(
                    new_paths,
                    self._directory(checkpoint_id) / "blobs",
                    save_blobs=True,
                )
                baseline.update(captured)
                observed.update(captured)
                total = sum(item.size for item in baseline.values())
                if total > self.max_bytes:
                    raise CheckpointError(
                        f"Scoped recovery is {total} bytes; limit is {self.max_bytes}"
                    )
            updated_status = CheckpointStatus(
                status.policy,
                status.coverage,
                status.degraded_reason,
                scoped_paths,
                status.uncovered_effects,
            )
            self._write_manifest(
                self._directory(checkpoint_id),
                _Manifest(baseline, observed, updated_status),
            )
            return status.degraded_reason

    def record_effect(self, checkpoint_id: str) -> ChangeSummary:
        """Record the exact post-effect tree used for later conflict detection."""
        with self._lock:
            manifest = self._load_manifest(checkpoint_id)
            coverage = manifest.status.coverage
            if coverage is RecoveryCoverage.NONE:
                return ChangeSummary((), (), ())
            paths = (
                self._listed_paths()
                if coverage is RecoveryCoverage.FULL
                else list(manifest.status.scoped_paths)
            )
            current = self._capture(paths, None, save_blobs=False)
            self._write_manifest(
                self._directory(checkpoint_id),
                _Manifest(manifest.baseline, current, manifest.status),
            )
            return _changes(manifest.baseline, current)

    def changes(self, checkpoint_id: str) -> ChangeSummary:
        with self._lock:
            manifest = self._load_manifest(checkpoint_id)
            return _changes(manifest.baseline, manifest.observed)

    def status(self, checkpoint_id: str) -> CheckpointStatus:
        with self._lock:
            return self._load_manifest(checkpoint_id).status

    def refresh_read_only(self, checkpoint_id: str) -> ChangeSummary:
        """Report changes without claiming externally changed bytes as Agent output."""
        with self._lock:
            manifest = self._load_manifest(checkpoint_id)
            paths = (
                self._listed_paths()
                if manifest.status.coverage is RecoveryCoverage.FULL
                else list(manifest.status.scoped_paths)
            )
            current = self._capture(paths, None, save_blobs=False)
            conflicts = _state_differences(manifest.observed, current)
            if conflicts:
                raise RollbackConflict(conflicts)
            return _changes(manifest.baseline, manifest.observed)

    def rollback(
        self, checkpoint_id: str, *, allow_partial: bool = False
    ) -> ChangeSummary:
        with self._lock:
            if self._running_tasks():
                raise CheckpointError("Stop all execution sessions before rollback")
            if self._running_agents():
                raise CheckpointError("Stop all child Agents before rollback")
            manifest = self._load_manifest(checkpoint_id)
            status = manifest.status
            if status.coverage is RecoveryCoverage.NONE:
                raise CheckpointError(
                    "Rollback is unavailable because application checkpointing is off"
                )
            if status.partial and not allow_partial:
                raise CheckpointError(
                    "Rollback coverage is partial; use /rollback --partial to restore "
                    "only protected files"
                )
            paths = (
                self._listed_paths()
                if status.coverage is RecoveryCoverage.FULL
                else list(status.scoped_paths)
            )
            current = self._capture(paths, None, save_blobs=False)
            conflicts = _state_differences(manifest.observed, current)
            if conflicts:
                raise RollbackConflict(conflicts)

            directory = self._directory(checkpoint_id)
            for relative in sorted(
                set(manifest.observed) - set(manifest.baseline), reverse=True
            ):
                target = self._target(relative)
                if target.is_symlink() or target.is_file():
                    target.unlink()
            for relative, state in manifest.baseline.items():
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
            self._write_manifest(
                directory,
                _Manifest(manifest.baseline, manifest.baseline, status),
            )
            return _changes(manifest.baseline, manifest.observed)

    def accept(self, checkpoint_id: str) -> ChangeSummary:
        with self._lock:
            changes = self.changes(checkpoint_id)
            shutil.rmtree(self._directory(checkpoint_id))
            return changes

    def diff_text(self, checkpoint_id: str) -> str:
        with self._lock:
            manifest = self._load_manifest(checkpoint_id)
            if manifest.status.coverage is RecoveryCoverage.NONE:
                return self.git_diff_text()
            baseline = manifest.baseline
            observed = manifest.observed
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

    def git_diff_text(self) -> str:
        """Return an unattributed bounded working-tree diff when Git is available."""
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.project_root),
                    "diff",
                    "--no-ext-diff",
                    "--",
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError:
            return "Diff unavailable: checkpointing is off and Git is not installed."
        if result.returncode != 0:
            return "Diff unavailable: checkpointing is off in a non-Git project."
        text = result.stdout.decode("utf-8", errors="replace")
        status = subprocess.run(
            [
                "git",
                "-C",
                str(self.project_root),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
        untracked = ""
        if status.returncode == 0:
            names = [
                line[3:]
                for line in status.stdout.decode("utf-8", errors="replace").splitlines()
                if line.startswith("?? ")
            ]
            if names:
                untracked = "\nUntracked files (content not shown):\n" + "\n".join(
                    f"?? {name}" for name in names
                )
        rendered = (text + untracked).strip() or "No Git working-tree changes."
        return (
            "Unattributed Git working-tree diff; changes may predate this Agent stage.\n\n"
            + rendered[:MAX_DIFF_CHARS]
        )

    def exists(self, checkpoint_id: str) -> bool:
        return (self._directory(checkpoint_id) / "manifest.json").is_file()

    def _is_git_project(self) -> bool:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.project_root), "rev-parse", "--is-inside-work-tree"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError:
            return False
        return result.returncode == 0 and result.stdout.strip() == b"true"

    def _scoped_relative_paths(
        self, paths: tuple[str, ...] | None
    ) -> tuple[str, ...] | None:
        if paths is None:
            return None
        relatives: list[str] = []
        for value in paths:
            candidate = Path(value)
            absolute = (
                candidate.resolve()
                if candidate.is_absolute()
                else (self.project_root / candidate).resolve()
            )
            try:
                relative = absolute.relative_to(self.project_root).as_posix()
            except ValueError:
                return None
            relatives.append(relative)
        return tuple(sorted(set(relatives)))

    def _append_uncovered_effect(
        self, checkpoint_id: str, manifest: _Manifest, effect_label: str
    ) -> None:
        status = manifest.status
        effects = status.uncovered_effects
        if len(effects) >= MAX_UNCOVERED_EFFECTS:
            effects = effects[:-1] + ("additional-uncovered-effects",)
        else:
            effects = effects + (effect_label,)
        updated_status = CheckpointStatus(
            status.policy,
            status.coverage,
            status.degraded_reason,
            status.scoped_paths,
            effects,
        )
        self._write_manifest(
            self._directory(checkpoint_id),
            _Manifest(manifest.baseline, manifest.observed, updated_status),
        )

    def _listed_paths(self) -> list[str]:
        try:
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
        except FileNotFoundError:
            return self._filesystem_paths()
        if result.returncode == 0:
            return sorted(
                os.fsdecode(item) for item in result.stdout.split(b"\0") if item
            )
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        if "not a git repository" in detail.casefold():
            return self._filesystem_paths()
        raise CheckpointError(f"Cannot enumerate rollback files: {detail}")

    def _filesystem_paths(self) -> list[str]:
        """Enumerate a non-Git project without making Git a runtime dependency."""
        paths: list[str] = []
        try:
            for current, directories, filenames in os.walk(
                self.project_root, topdown=True, followlinks=False
            ):
                current_path = Path(current)
                retained: list[str] = []
                for name in directories:
                    candidate = current_path / name
                    if current_path == self.project_root and name.casefold() in {
                        ".git",
                        ".coding-kid",
                    }:
                        continue
                    if candidate.is_symlink():
                        paths.append(
                            candidate.relative_to(self.project_root).as_posix()
                        )
                    else:
                        retained.append(name)
                directories[:] = retained
                for name in filenames:
                    candidate = current_path / name
                    if candidate.is_file() or candidate.is_symlink():
                        paths.append(
                            candidate.relative_to(self.project_root).as_posix()
                        )
                if len(paths) > self.max_files:
                    raise CheckpointError(
                        f"Checkpoint has more than {self.max_files} files; limit is "
                        f"{self.max_files}"
                    )
        except OSError as error:
            raise CheckpointError(
                f"Cannot enumerate rollback files without Git: {error}"
            ) from error
        return sorted(paths)

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
        current = self.project_root
        for component in Path(relative).parts[:-1]:
            current /= component
            if current.is_symlink():
                raise CheckpointError(
                    f"Checkpoint path crosses a symbolic-link directory: {relative}"
                )
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

    def _write_manifest(self, directory: Path, manifest: _Manifest) -> None:
        status = manifest.status
        payload = {
            "version": 2,
            "project_root": str(self.project_root),
            "policy": status.policy.value,
            "coverage": status.coverage.value,
            "degraded_reason": status.degraded_reason,
            "scoped_paths": list(status.scoped_paths),
            "uncovered_effects": list(status.uncovered_effects),
            "uncovered_effect_counts": {
                label: status.uncovered_effects.count(label)
                for label in sorted(set(status.uncovered_effects))
            },
            "baseline": {
                key: value.to_dict() for key, value in manifest.baseline.items()
            },
            "observed": {
                key: value.to_dict() for key, value in manifest.observed.items()
            },
        }
        temporary = directory / "manifest.json.tmp"
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        temporary.replace(directory / "manifest.json")

    def _load_manifest(self, checkpoint_id: str) -> _Manifest:
        directory = self._directory(checkpoint_id)
        try:
            payload = json.loads(
                (directory / "manifest.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            raise CheckpointError(
                f"Cannot load checkpoint {checkpoint_id}: {error}"
            ) from error
        version = payload.get("version")
        if version not in {1, 2} or payload.get("project_root") != str(
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
        if version == 1:
            status = CheckpointStatus(
                CheckpointPolicy.REQUIRED,
                RecoveryCoverage.FULL,
                None,
                (),
                (),
            )
        else:
            try:
                status = CheckpointStatus(
                    CheckpointPolicy(payload["policy"]),
                    RecoveryCoverage(payload["coverage"]),
                    (
                        str(payload["degraded_reason"])
                        if payload.get("degraded_reason") is not None
                        else None
                    ),
                    tuple(str(item) for item in payload.get("scoped_paths", [])),
                    tuple(
                        str(item) for item in payload.get("uncovered_effects", [])
                    ),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise CheckpointError("Invalid checkpoint recovery metadata") from error
        return _Manifest(baseline, observed, status)

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
