from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

from coding_kid.checkpoints import (
    CheckpointError,
    CheckpointManager,
    RollbackConflict,
)


def _git(path: Path, *arguments: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(path), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / ".gitignore").write_text("ignored.bin\n", encoding="utf-8")
    (root / "tracked.txt").write_text("committed\n", encoding="utf-8")
    _git(root, "add", ".gitignore", "tracked.txt")
    _git(root, "commit", "-qm", "base")
    return root


def test_rollback_preserves_preexisting_dirty_and_untracked_bytes(
    project: Path, tmp_path: Path
) -> None:
    dirty = "用户原有改动\n".encode()
    (project / "tracked.txt").write_bytes(dirty)
    (project / "before.bin").write_bytes(b"\x00before\xff")
    (project / "empty.txt").write_bytes(b"")
    manager = CheckpointManager(project, tmp_path / "state")
    checkpoint = manager.create()

    manager.prepare_effect(checkpoint)
    (project / "tracked.txt").write_text("agent\n", encoding="utf-8")
    (project / "before.bin").unlink()
    (project / "empty.txt").write_text("nonempty", encoding="utf-8")
    (project / "new.txt").write_text("new", encoding="utf-8")
    manager.record_effect(checkpoint)

    changes = manager.rollback(checkpoint)
    assert (project / "tracked.txt").read_bytes() == dirty
    assert (project / "before.bin").read_bytes() == b"\x00before\xff"
    assert (project / "empty.txt").read_bytes() == b""
    assert not (project / "new.txt").exists()
    assert changes.modified == ("empty.txt", "tracked.txt")
    assert changes.deleted == ("before.bin",)
    assert changes.created == ("new.txt",)


def test_rollback_handles_rename_as_delete_and_create(
    project: Path, tmp_path: Path
) -> None:
    manager = CheckpointManager(project, tmp_path / "state")
    checkpoint = manager.create()
    manager.prepare_effect(checkpoint)
    (project / "tracked.txt").rename(project / "renamed.txt")
    manager.record_effect(checkpoint)

    manager.rollback(checkpoint)

    assert (project / "tracked.txt").read_text(encoding="utf-8") == "committed\n"
    assert not (project / "renamed.txt").exists()


def test_ignored_file_is_neither_snapshotted_nor_removed(
    project: Path, tmp_path: Path
) -> None:
    ignored = project / "ignored.bin"
    ignored.write_bytes(b"before")
    manager = CheckpointManager(project, tmp_path / "state")
    checkpoint = manager.create()
    ignored.write_bytes(b"after")

    manager.rollback(checkpoint)

    assert ignored.read_bytes() == b"after"


def test_external_modification_refuses_effect_and_rollback(
    project: Path, tmp_path: Path
) -> None:
    manager = CheckpointManager(project, tmp_path / "state")
    checkpoint = manager.create()
    (project / "tracked.txt").write_text("external", encoding="utf-8")

    with pytest.raises(RollbackConflict) as before:
        manager.prepare_effect(checkpoint)
    assert before.value.paths == ("tracked.txt",)
    with pytest.raises(RollbackConflict):
        manager.rollback(checkpoint)
    assert (project / "tracked.txt").read_text(encoding="utf-8") == "external"


@pytest.mark.parametrize("kind", ["task", "agent"])
def test_running_work_refuses_rollback(
    project: Path, tmp_path: Path, kind: str
) -> None:
    manager = CheckpointManager(
        project,
        tmp_path / "state",
        running_tasks=(lambda: 1 if kind == "task" else 0),
        running_agents=(lambda: 1 if kind == "agent" else 0),
    )
    checkpoint = manager.create()

    with pytest.raises(CheckpointError, match="Stop all"):
        manager.rollback(checkpoint)


def test_checkpoint_size_and_file_limits_fail_closed(
    project: Path, tmp_path: Path
) -> None:
    with pytest.raises(CheckpointError, match="exceeds"):
        CheckpointManager(project, tmp_path / "small", max_bytes=1).create()
    with pytest.raises(CheckpointError, match="limit"):
        CheckpointManager(project, tmp_path / "few", max_files=1).create()


def test_diff_is_bounded_and_accept_removes_protected_snapshot(
    project: Path, tmp_path: Path
) -> None:
    state = tmp_path / "state"
    manager = CheckpointManager(project, state)
    checkpoint = manager.create()
    manager.prepare_effect(checkpoint)
    (project / "tracked.txt").write_text("changed\n", encoding="utf-8")
    manager.record_effect(checkpoint)

    assert "-committed" in manager.diff_text(checkpoint)
    assert "+changed" in manager.diff_text(checkpoint)
    changes = manager.accept(checkpoint)
    assert changes.modified == ("tracked.txt",)
    assert not manager.exists(checkpoint)


@pytest.mark.skipif(
    os.name == "nt", reason="symlink creation is not generally available"
)
def test_symlink_round_trip(project: Path, tmp_path: Path) -> None:
    link = project / "link"
    os.symlink("tracked.txt", link)
    manager = CheckpointManager(project, tmp_path / "state")
    checkpoint = manager.create()
    manager.prepare_effect(checkpoint)
    link.unlink()
    os.symlink("elsewhere", link)
    manager.record_effect(checkpoint)

    manager.rollback(checkpoint)

    assert link.is_symlink()
    assert os.readlink(link) == "tracked.txt"
