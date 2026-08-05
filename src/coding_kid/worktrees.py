"""Application-owned Git worktrees for isolated child Agent changes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from threading import RLock
from typing import Literal


MAX_WORKSPACE_FILES = 10_000
MAX_WORKSPACE_BYTES = 100 * 1024 * 1024
MAX_WORKSPACE_DIFF_CHARS = 50_000
_AGENT_ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")

WorkspaceStatus = Literal[
    "active",
    "ready",
    "conflicted",
    "integrated_pending",
    "integrated",
    "discarded",
    "orphaned",
]


class WorktreeError(RuntimeError):
    """Raised when an isolated workspace cannot be managed safely."""


@dataclass
class WorkspaceRecord:
    agent_id: str
    path: str
    branch: str
    baseline_commit: str
    head_commit: str
    status: WorkspaceStatus
    changed_files: int = 0
    conflict_paths: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: object) -> WorkspaceRecord:
        if not isinstance(value, dict):
            raise WorktreeError("Invalid workspace manifest")
        try:
            status = str(value["status"])
            if status not in {
                "active",
                "ready",
                "conflicted",
                "integrated_pending",
                "integrated",
                "discarded",
                "orphaned",
            }:
                raise ValueError(status)
            return cls(
                agent_id=str(value["agent_id"]),
                path=str(value["path"]),
                branch=str(value["branch"]),
                baseline_commit=str(value["baseline_commit"]),
                head_commit=str(value["head_commit"]),
                status=status,  # type: ignore[arg-type]
                changed_files=int(value.get("changed_files", 0)),
                conflict_paths=tuple(str(item) for item in value.get("conflict_paths", [])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise WorktreeError("Invalid workspace manifest") from error

    def model_text(self) -> str:
        conflicts = ", ".join(self.conflict_paths) or "none"
        return (
            f"workspace_status: {self.status}\n"
            f"workspace_path: {self.path}\n"
            f"workspace_branch: {self.branch}\n"
            f"baseline_commit: {self.baseline_commit}\n"
            f"head_commit: {self.head_commit}\n"
            f"changed_files: {self.changed_files}\n"
            f"conflict_paths: {conflicts}"
        )


@dataclass(frozen=True)
class _UntrackedFile:
    relative: str
    kind: str
    content: bytes


@dataclass(frozen=True)
class _RootSnapshot:
    patch: bytes
    untracked: tuple[_UntrackedFile, ...]
    fingerprint: str


class WorktreeManager:
    """Create, review, reconcile, and retire Coding Kid-owned worktrees."""

    def __init__(self, project_root: Path, state_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.state_root = state_root.resolve()
        self.workspaces_root = self.state_root / "workspaces"
        self.manifests_root = self.state_root / "manifests"
        self.workspaces_root.mkdir(parents=True, exist_ok=True)
        self.manifests_root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._require_repository()

    def create(self, agent_id: str) -> WorkspaceRecord:
        """Create one isolated worktree containing a stable dirty-root baseline."""
        self._validate_agent_id(agent_id)
        with self._lock:
            if self._manifest_path(agent_id).exists():
                raise WorktreeError(f"Workspace already exists for {agent_id}")
            snapshot = self._capture_root()
            record = self._create_from_snapshot(agent_id, snapshot)
            if self._capture_root().fingerprint != snapshot.fingerprint:
                self._remove_owned(record, delete_manifest=True)
                raise WorktreeError(
                    "Root worktree changed while the isolated baseline was created"
                )
            return record

    def get(self, agent_id: str) -> WorkspaceRecord:
        self._validate_agent_id(agent_id)
        path = self._manifest_path(agent_id)
        try:
            record = WorkspaceRecord.from_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except FileNotFoundError as error:
            raise WorktreeError(f"No isolated workspace for {agent_id}") from error
        except (OSError, ValueError) as error:
            raise WorktreeError(f"Cannot read workspace manifest for {agent_id}") from error
        self._validate_record(record)
        return record

    def list(self) -> tuple[WorkspaceRecord, ...]:
        records: list[WorkspaceRecord] = []
        for manifest in sorted(self.manifests_root.glob("*.json")):
            try:
                records.append(self.get(manifest.stem))
            except WorktreeError:
                continue
        return tuple(records)

    def mark_active_as_orphaned(self) -> None:
        """Retain interrupted workspace evidence across application restarts."""
        with self._lock:
            for record in self.list():
                if record.status == "active":
                    record.status = "orphaned"
                    self._save(record)

    def activate(self, agent_id: str) -> WorkspaceRecord:
        with self._lock:
            record = self.get(agent_id)
            if record.status not in {"ready", "conflicted", "orphaned"}:
                raise WorktreeError(
                    f"Workspace {agent_id} cannot run from {record.status}"
                )
            record.status = "active"
            record.conflict_paths = ()
            self._save(record)
            return record

    def finalize(self, agent_id: str) -> WorkspaceRecord:
        """Commit one completed child delta without touching the root worktree."""
        with self._lock:
            record = self.get(agent_id)
            if record.status != "active":
                raise WorktreeError(
                    f"Workspace {agent_id} cannot finalize from {record.status}"
                )
            self._validate_git_identity(record)
            self._git(Path(record.path), ["add", "-A"])
            conflicts = self._conflict_paths(Path(record.path))
            if conflicts:
                record.status = "conflicted"
                record.conflict_paths = conflicts
                self._save(record)
                return record
            check = self._git(Path(record.path), ["diff", "--check"], check=False)
            if check.returncode != 0:
                raise WorktreeError(self._detail(check, "Workspace diff check failed"))
            staged = self._git(
                Path(record.path), ["diff", "--cached", "--quiet"], check=False
            )
            if staged.returncode not in {0, 1}:
                raise WorktreeError(self._detail(staged, "Cannot inspect workspace changes"))
            if staged.returncode == 1:
                self._commit(Path(record.path), f"Coding Kid Agent {agent_id} changes")
            record.head_commit = self._head(Path(record.path))
            record.changed_files = len(self._changed_paths(record))
            record.status = "ready"
            record.conflict_paths = ()
            self._save(record)
            return record

    def fail(self, agent_id: str) -> WorkspaceRecord:
        """Preserve a failed child workspace as orphaned review evidence."""
        with self._lock:
            record = self.get(agent_id)
            if record.status == "active":
                record.status = "orphaned"
                record.changed_files = len(self._working_changed_paths(record))
                self._save(record)
            return record

    def diff_text(self, agent_id: str) -> str:
        record = self.get(agent_id)
        self._validate_git_identity(record)
        workspace = Path(record.path)
        stat = self._git(
            workspace,
            ["diff", "--stat", record.baseline_commit, "HEAD"],
        ).stdout.decode("utf-8", errors="replace").strip()
        names = self._git(
            workspace,
            ["diff", "--name-status", record.baseline_commit, "HEAD"],
        ).stdout.decode("utf-8", errors="replace").strip()
        patch = self._git(
            workspace,
            ["diff", "--no-ext-diff", record.baseline_commit, "HEAD"],
        ).stdout.decode("utf-8", errors="replace")
        text = f"{record.model_text()}\n\n{stat or 'No changes.'}"
        if names:
            text += f"\n\nChanged paths:\n{names}"
        if patch:
            text += f"\n\nDiff:\n{patch}"
        if len(text) > MAX_WORKSPACE_DIFF_CHARS:
            text = f"{text[:MAX_WORKSPACE_DIFF_CHARS]}\n... workspace diff truncated ..."
        return text

    def integrate(self, agent_id: str) -> WorkspaceRecord:
        """Apply one reviewed child delta to the root without creating a commit."""
        with self._lock:
            record = self.get(agent_id)
            if record.status not in {"ready", "orphaned"}:
                raise WorktreeError(
                    f"Workspace {agent_id} cannot integrate from {record.status}"
                )
            self._validate_git_identity(record)
            patch = self._result_patch(record)
            if patch:
                check = self._git(
                    self.project_root,
                    ["apply", "--check", "--binary", "-"],
                    input_bytes=patch,
                    check=False,
                )
                if check.returncode != 0:
                    paths = ", ".join(self._changed_paths(record)) or "unknown paths"
                    raise WorktreeError(
                        f"Child delta conflicts with the current root ({paths}); "
                        "reconcile it in isolation before retrying"
                    )
                self._git(
                    self.project_root,
                    ["apply", "--binary", "-"],
                    input_bytes=patch,
                )
            record.status = "integrated_pending"
            record.changed_files = len(self._changed_paths(record))
            self._save(record)
            return record

    def reconcile(self, agent_id: str) -> WorkspaceRecord:
        """Replay an old child delta over a new dirty-root baseline in isolation."""
        with self._lock:
            record = self.get(agent_id)
            if record.status not in {"ready", "orphaned"}:
                raise WorktreeError(
                    f"Workspace {agent_id} cannot reconcile from {record.status}"
                )
            patch = self._result_patch(record)
            snapshot = self._capture_root()
            self._remove_owned(record, delete_manifest=True)
            replacement = self._create_from_snapshot(agent_id, snapshot)
            if patch:
                applied = self._git(
                    Path(replacement.path),
                    ["apply", "--3way", "--binary", "-"],
                    input_bytes=patch,
                    check=False,
                )
                conflicts = self._conflict_paths(Path(replacement.path))
                if applied.returncode != 0 and not conflicts:
                    replacement.status = "orphaned"
                    self._save(replacement)
                    raise WorktreeError(
                        self._detail(applied, "Cannot replay child delta")
                    )
                if conflicts:
                    replacement.status = "conflicted"
                    replacement.conflict_paths = conflicts
                    replacement.changed_files = len(
                        self._working_changed_paths(replacement)
                    )
                    self._save(replacement)
                    return replacement
                replacement.status = "active"
                self._save(replacement)
                replacement = self.finalize(agent_id)
            return replacement

    def discard(self, agent_id: str, *, confirmed: bool) -> WorkspaceRecord:
        with self._lock:
            record = self.get(agent_id)
            if not confirmed:
                raise WorktreeError("discard requires confirm_discard=true")
            if record.status in {"active", "integrated_pending"}:
                raise WorktreeError(
                    f"Workspace {agent_id} cannot be discarded from {record.status}"
                )
            self._remove_owned(record, delete_manifest=False)
            record.status = "discarded"
            record.path = ""
            self._save(record)
            return record

    def accept_integrated(self) -> tuple[WorkspaceRecord, ...]:
        accepted: list[WorkspaceRecord] = []
        with self._lock:
            for record in self.list():
                if record.status != "integrated_pending":
                    continue
                self._remove_owned(record, delete_manifest=False)
                record.status = "integrated"
                record.path = ""
                self._save(record)
                accepted.append(record)
        return tuple(accepted)

    def rollback_integrated(self) -> tuple[WorkspaceRecord, ...]:
        restored: list[WorkspaceRecord] = []
        with self._lock:
            for record in self.list():
                if record.status == "integrated_pending":
                    record.status = "ready"
                    self._save(record)
                    restored.append(record)
        return tuple(restored)

    def _create_from_snapshot(
        self, agent_id: str, snapshot: _RootSnapshot
    ) -> WorkspaceRecord:
        workspace = (self.workspaces_root / agent_id).resolve()
        branch = f"coding-kid/agent/{agent_id}"
        self._assert_owned_path(workspace)
        created = self._git(
            self.project_root,
            ["worktree", "add", "-b", branch, str(workspace), "HEAD"],
            check=False,
        )
        if created.returncode != 0:
            raise WorktreeError(self._detail(created, "Cannot create Git worktree"))
        record = WorkspaceRecord(agent_id, str(workspace), branch, "", "", "active")
        try:
            if snapshot.patch:
                self._git(
                    workspace,
                    ["apply", "--index", "--binary", "-"],
                    input_bytes=snapshot.patch,
                )
            for item in snapshot.untracked:
                target = self._safe_target(workspace, item.relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                if item.kind == "symlink":
                    os.symlink(os.fsdecode(item.content), target)
                else:
                    target.write_bytes(item.content)
            self._git(workspace, ["add", "-A"])
            self._commit(workspace, f"Coding Kid workspace baseline for {agent_id}")
            head = self._head(workspace)
            record.baseline_commit = head
            record.head_commit = head
            self._save(record)
            return record
        except BaseException:
            self._remove_owned(record, delete_manifest=True)
            raise

    def _capture_root(self) -> _RootSnapshot:
        patch = self._git(
            self.project_root, ["diff", "--binary", "--full-index", "HEAD"]
        ).stdout
        raw_paths = self._git(
            self.project_root,
            ["ls-files", "--others", "--exclude-standard", "-z"],
        ).stdout.split(b"\0")
        paths = [os.fsdecode(item) for item in raw_paths if item]
        if len(paths) > MAX_WORKSPACE_FILES:
            raise WorktreeError(
                f"Dirty baseline has {len(paths)} untracked files; limit is "
                f"{MAX_WORKSPACE_FILES}"
            )
        total = len(patch)
        digest = hashlib.sha256(patch)
        files: list[_UntrackedFile] = []
        for relative in sorted(paths):
            target = self._safe_target(self.project_root, relative)
            if target.is_symlink():
                content = os.fsencode(os.readlink(target))
                kind = "symlink"
            elif target.is_file():
                content = target.read_bytes()
                kind = "file"
            else:
                raise WorktreeError(f"Unsupported untracked entry: {relative}")
            total += len(content)
            if total > MAX_WORKSPACE_BYTES:
                raise WorktreeError(
                    f"Dirty baseline exceeds {MAX_WORKSPACE_BYTES} bytes"
                )
            digest.update(relative.encode("utf-8", errors="surrogateescape"))
            digest.update(kind.encode("ascii"))
            digest.update(content)
            files.append(_UntrackedFile(relative, kind, content))
        return _RootSnapshot(patch, tuple(files), digest.hexdigest())

    def _result_patch(self, record: WorkspaceRecord) -> bytes:
        return self._git(
            Path(record.path),
            ["diff", "--binary", "--full-index", record.baseline_commit, "HEAD"],
        ).stdout

    def _changed_paths(self, record: WorkspaceRecord) -> tuple[str, ...]:
        output = self._git(
            Path(record.path),
            ["diff", "--name-only", "-z", record.baseline_commit, "HEAD"],
        ).stdout
        return tuple(os.fsdecode(item) for item in output.split(b"\0") if item)

    def _working_changed_paths(self, record: WorkspaceRecord) -> tuple[str, ...]:
        output = self._git(
            Path(record.path), ["status", "--porcelain", "-z"]
        ).stdout
        paths: list[str] = []
        for item in output.split(b"\0"):
            if len(item) > 3:
                paths.append(os.fsdecode(item[3:]))
        return tuple(paths)

    def _conflict_paths(self, workspace: Path) -> tuple[str, ...]:
        output = self._git(
            workspace, ["diff", "--name-only", "--diff-filter=U", "-z"]
        ).stdout
        return tuple(os.fsdecode(item) for item in output.split(b"\0") if item)

    def _validate_git_identity(self, record: WorkspaceRecord) -> None:
        workspace = Path(record.path).resolve()
        self._assert_owned_path(workspace)
        if not workspace.is_dir():
            raise WorktreeError(f"Owned workspace is missing: {workspace}")
        branch = self._git(
            workspace, ["symbolic-ref", "--quiet", "--short", "HEAD"], check=False
        )
        actual = branch.stdout.decode("utf-8", errors="replace").strip()
        if branch.returncode != 0 or actual != record.branch:
            raise WorktreeError("Workspace branch identity changed; refusing operation")
        ancestor = self._git(
            workspace,
            ["merge-base", "--is-ancestor", record.baseline_commit, "HEAD"],
            check=False,
        )
        if ancestor.returncode != 0:
            raise WorktreeError("Workspace baseline is no longer an ancestor of HEAD")

    def _validate_record(self, record: WorkspaceRecord) -> None:
        self._validate_agent_id(record.agent_id)
        if record.path:
            self._assert_owned_path(Path(record.path).resolve())
        if record.branch != f"coding-kid/agent/{record.agent_id}":
            raise WorktreeError("Workspace manifest has an unexpected branch")

    def _remove_owned(self, record: WorkspaceRecord, *, delete_manifest: bool) -> None:
        if record.path:
            workspace = Path(record.path).resolve()
            self._assert_owned_path(workspace)
            self._git(
                self.project_root,
                ["worktree", "remove", "--force", str(workspace)],
                check=False,
            )
            if workspace.exists():
                shutil.rmtree(workspace, ignore_errors=True)
        self._git(
            self.project_root,
            ["branch", "-D", record.branch],
            check=False,
        )
        if delete_manifest:
            self._manifest_path(record.agent_id).unlink(missing_ok=True)

    def _commit(self, workspace: Path, message: str) -> None:
        self._git(
            workspace,
            [
                "-c",
                "user.name=Coding Kid",
                "-c",
                "user.email=coding-kid@local",
                "-c",
                "commit.gpgSign=false",
                "commit",
                "--no-verify",
                "--allow-empty",
                "-m",
                message,
            ],
        )

    def _head(self, workspace: Path) -> str:
        return self._git(workspace, ["rev-parse", "HEAD"]).stdout.decode().strip()

    def _save(self, record: WorkspaceRecord) -> None:
        self._validate_record(record)
        destination = self._manifest_path(record.agent_id)
        temporary = destination.with_suffix(".tmp")
        payload = asdict(record)
        payload["conflict_paths"] = list(record.conflict_paths)
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        temporary.replace(destination)

    def _manifest_path(self, agent_id: str) -> Path:
        self._validate_agent_id(agent_id)
        return self.manifests_root / f"{agent_id}.json"

    def _assert_owned_path(self, path: Path) -> None:
        try:
            relative = path.relative_to(self.workspaces_root)
        except ValueError as error:
            raise WorktreeError(f"Workspace path is not application-owned: {path}") from error
        if len(relative.parts) != 1 or not _AGENT_ID.fullmatch(relative.name):
            raise WorktreeError(f"Invalid owned workspace path: {path}")

    def _safe_target(self, root: Path, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
            raise WorktreeError(f"Unsafe Git path: {relative}")
        target = Path(os.path.abspath(root / candidate))
        try:
            target.relative_to(root.resolve())
        except ValueError as error:
            raise WorktreeError(f"Git path escapes workspace: {relative}") from error
        current = root.resolve()
        for part in candidate.parts[:-1]:
            current /= part
            if current.is_symlink():
                raise WorktreeError(f"Git path crosses a symlink: {relative}")
        return target

    def _validate_agent_id(self, agent_id: str) -> None:
        if not _AGENT_ID.fullmatch(agent_id):
            raise WorktreeError("Invalid Agent ID for isolated workspace")

    def _require_repository(self) -> None:
        result = self._git(
            self.project_root, ["rev-parse", "--show-toplevel"], check=False
        )
        if result.returncode != 0:
            raise WorktreeError("Isolated Agents require a Git repository")

    def _git(
        self,
        cwd: Path,
        arguments: list[str],
        *,
        input_bytes: bytes | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        result = subprocess.run(
            ["git", "-C", str(cwd), *arguments],
            input=input_bytes,
            stdin=subprocess.DEVNULL if input_bytes is None else None,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if check and result.returncode != 0:
            raise WorktreeError(self._detail(result, f"Git {' '.join(arguments)} failed"))
        return result

    @staticmethod
    def _detail(result: subprocess.CompletedProcess[bytes], prefix: str) -> str:
        detail = (result.stderr or result.stdout).decode(
            "utf-8", errors="replace"
        ).strip()
        return f"{prefix}: {detail}" if detail else prefix
