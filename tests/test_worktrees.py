from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess

import pytest

from coding_kid.worktrees import WorktreeError, WorktreeManager


def git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def repository(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "project"
    state = tmp_path / "state"
    root.mkdir(parents=True)
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Test User")
    git(root, "config", "user.email", "test@example.com")
    (root / "app.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", "app.txt")
    git(root, "commit", "-m", "base")
    return root, state


def test_workspace_captures_dirty_root_but_isolates_child_delta(
    tmp_path: Path,
) -> None:
    root, state = repository(tmp_path)
    (root / "app.txt").write_text("dirty root\n", encoding="utf-8")
    (root / "note.txt").write_text("untracked ü\n", encoding="utf-8")

    manager = WorktreeManager(root, state)
    record = manager.create("agent_one")
    workspace = Path(record.path)

    assert (workspace / "app.txt").read_text(encoding="utf-8") == "dirty root\n"
    assert (workspace / "note.txt").read_text(encoding="utf-8") == "untracked ü\n"
    assert (root / "app.txt").read_text(encoding="utf-8") == "dirty root\n"

    (workspace / "app.txt").write_text("child result\n", encoding="utf-8")
    (workspace / "child.txt").write_text("new\n", encoding="utf-8")
    ready = manager.finalize("agent_one")

    assert ready.status == "ready"
    assert ready.changed_files == 2
    assert (root / "app.txt").read_text(encoding="utf-8") == "dirty root\n"
    assert not (root / "child.txt").exists()
    assert "app.txt" in manager.diff_text("agent_one")

    pending = manager.integrate("agent_one")
    assert pending.status == "integrated_pending"
    assert (root / "app.txt").read_text(encoding="utf-8") == "child result\n"
    assert (root / "child.txt").read_text(encoding="utf-8") == "new\n"

    accepted = manager.accept_integrated()
    assert [item.agent_id for item in accepted] == ["agent_one"]
    assert manager.get("agent_one").status == "integrated"
    assert not workspace.exists()


def test_parallel_workspaces_can_edit_the_same_path(tmp_path: Path) -> None:
    root, state = repository(tmp_path)
    manager = WorktreeManager(root, state)
    first = manager.create("agent_a")
    second = manager.create("agent_b")

    Path(first.path, "app.txt").write_text("first\n", encoding="utf-8")
    Path(second.path, "app.txt").write_text("second\n", encoding="utf-8")
    manager.finalize("agent_a")
    manager.finalize("agent_b")

    assert (root / "app.txt").read_text(encoding="utf-8") == "base\n"
    assert Path(first.path, "app.txt").read_text() == "first\n"
    assert Path(second.path, "app.txt").read_text() == "second\n"


def test_conflict_is_reconciled_inside_workspace(tmp_path: Path) -> None:
    root, state = repository(tmp_path)
    manager = WorktreeManager(root, state)
    record = manager.create("agent_conflict")
    workspace = Path(record.path)
    (workspace / "app.txt").write_text("child\n", encoding="utf-8")
    manager.finalize("agent_conflict")
    (root / "app.txt").write_text("root advanced\n", encoding="utf-8")

    with pytest.raises(WorktreeError, match="reconcile"):
        manager.integrate("agent_conflict")
    assert (root / "app.txt").read_text(encoding="utf-8") == "root advanced\n"

    reconciled = manager.reconcile("agent_conflict")
    assert reconciled.status == "conflicted"
    assert reconciled.conflict_paths == ("app.txt",)
    assert "<<<<<<<" in Path(reconciled.path, "app.txt").read_text()

    manager.activate("agent_conflict")
    Path(reconciled.path, "app.txt").write_text(
        "root advanced + child\n", encoding="utf-8"
    )
    manager.finalize("agent_conflict")
    manager.integrate("agent_conflict")
    assert (root / "app.txt").read_text() == "root advanced + child\n"


def test_pending_integration_can_be_rolled_back_and_retried(tmp_path: Path) -> None:
    root, state = repository(tmp_path)
    manager = WorktreeManager(root, state)
    record = manager.create("agent_retry")
    Path(record.path, "app.txt").write_text("result\n", encoding="utf-8")
    manager.finalize("agent_retry")
    manager.integrate("agent_retry")

    (root / "app.txt").write_text("base\n", encoding="utf-8")
    restored = manager.rollback_integrated()

    assert [item.status for item in restored] == ["ready"]
    assert manager.integrate("agent_retry").status == "integrated_pending"


def test_discard_requires_confirmation_and_never_targets_manual_worktree(
    tmp_path: Path,
) -> None:
    root, state = repository(tmp_path)
    manager = WorktreeManager(root, state)
    record = manager.create("agent_drop")
    manager.finalize("agent_drop")

    with pytest.raises(WorktreeError, match="confirm_discard"):
        manager.discard("agent_drop", confirmed=False)

    discarded = manager.discard("agent_drop", confirmed=True)
    assert discarded.status == "discarded"
    assert not Path(record.path).exists()
    assert git(root, "branch", "--list", "coding-kid/agent/agent_drop") == ""


def test_active_workspace_becomes_orphaned_after_restart(tmp_path: Path) -> None:
    root, state = repository(tmp_path)
    first = WorktreeManager(root, state)
    first.create("agent_lost")

    restarted = WorktreeManager(root, state)
    restarted.mark_active_as_orphaned()

    assert restarted.get("agent_lost").status == "orphaned"


def test_non_repository_and_invalid_agent_id_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "plain"
    root.mkdir()
    with pytest.raises(WorktreeError, match="Git repository"):
        WorktreeManager(root, tmp_path / "state")

    project, state = repository(tmp_path / "repo-case")
    manager = WorktreeManager(project, state)
    with pytest.raises(WorktreeError, match="Invalid Agent ID"):
        manager.create("../escape")


def test_ten_round_overlapping_worktree_stress_isolated_and_cleans_up(
    tmp_path: Path,
) -> None:
    root, state = repository(tmp_path)
    target = root / "overlap.txt"
    target.write_text("root\n", encoding="utf-8")
    git(root, "add", "overlap.txt")
    git(root, "commit", "-m", "add overlap")
    manager = WorktreeManager(root, state)

    for round_index in range(10):
        agent_ids = [f"stress_{round_index}_{worker}" for worker in range(4)]
        with ThreadPoolExecutor(max_workers=4) as executor:
            records = tuple(executor.map(manager.create, agent_ids))
        for worker, record in enumerate(records):
            Path(record.path, "overlap.txt").write_text(
                f"round {round_index} worker {worker}\n", encoding="utf-8"
            )
        with ThreadPoolExecutor(max_workers=4) as executor:
            ready = tuple(executor.map(manager.finalize, agent_ids))
        assert all(record.status == "ready" for record in ready)
        assert target.read_text(encoding="utf-8") == "root\n"
        assert len({manager.diff_text(agent_id) for agent_id in agent_ids}) == 4
        for agent_id in agent_ids:
            discarded = manager.discard(agent_id, confirmed=True)
            assert discarded.status == "discarded"

    assert target.read_text(encoding="utf-8") == "root\n"
    assert not tuple((state / "workspaces").iterdir())
