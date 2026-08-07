from __future__ import annotations

import os
from pathlib import Path

import pytest

import coding_kid.patching as patching
from coding_kid.patching import PatchError, apply_patch_text, parse_patch
from coding_kid.permissions import ToolEffect
from coding_kid.sandbox import SandboxConfig, SandboxMode, SandboxRuntime
from coding_kid.tools import build_tool_registry


def _apply(root: Path, body: str) -> str:
    sandbox = SandboxRuntime(
        SandboxConfig(SandboxMode.DANGER_FULL_ACCESS, root, root)
    )
    return apply_patch_text(body, sandbox_runtime=sandbox)


def test_multi_file_multi_hunk_add_update_delete_and_unicode(tmp_path: Path) -> None:
    (tmp_path / "source.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    (tmp_path / "old.txt").write_text("remove me\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: source.txt
@@
-alpha
+你好
@@
-gamma
+omega
*** Add File: added.txt
+new
+内容
*** Delete File: old.txt
*** End Patch"""

    result = _apply(tmp_path, patch)

    assert "3 file(s)" in result
    assert (tmp_path / "source.txt").read_text(encoding="utf-8") == "你好\nbeta\nomega\n"
    assert (tmp_path / "added.txt").read_text(encoding="utf-8") == "new\n内容\n"
    assert not (tmp_path / "old.txt").exists()


def test_update_preserves_crlf_and_missing_final_newline(tmp_path: Path) -> None:
    (tmp_path / "windows.txt").write_bytes(b"alpha\r\nbeta\r\n")
    (tmp_path / "noeol.txt").write_bytes(b"value=1")

    _apply(
        tmp_path,
        """*** Begin Patch
*** Update File: windows.txt
@@
-beta
+updated
*** Update File: noeol.txt
@@
-value=1
+value=2
*** End Patch""",
    )

    assert (tmp_path / "windows.txt").read_bytes() == b"alpha\r\nupdated\r\n"
    assert (tmp_path / "noeol.txt").read_bytes() == b"value=2"


@pytest.mark.parametrize(
    "patch, message",
    [
        ("*** Update File: a\n*** End Patch", "Begin Patch"),
        ("*** Begin Patch\n*** Move File: a\n*** End Patch", "invalid file marker"),
        ("*** Begin Patch\n*** Add File: ../a\n+x\n*** End Patch", "invalid"),
        ("*** Begin Patch\n*** Add File: .git/config\n+x\n*** End Patch", "protected"),
        (
            "*** Begin Patch\n*** Add File: a\n+x\n*** Add File: a\n+y\n*** End Patch",
            "duplicate",
        ),
        ("*** Begin Patch\n*** Delete File: absent\n+bad\n*** End Patch", "must not"),
    ],
)
def test_invalid_patch_syntax_and_paths_are_rejected(
    patch: str, message: str
) -> None:
    with pytest.raises(PatchError, match=message):
        parse_patch(patch)


def test_validation_failure_in_later_file_makes_zero_modifications(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("before\n", encoding="utf-8")
    second.write_text("actual\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: first.txt
@@
-before
+after
*** Update File: second.txt
@@
-missing
+replacement
*** End Patch"""

    with pytest.raises(PatchError, match="hunk 1"):
        _apply(tmp_path, patch)

    assert first.read_text(encoding="utf-8") == "before\n"
    assert second.read_text(encoding="utf-8") == "actual\n"


def test_repeated_hunk_context_is_rejected_with_bounded_diagnostic(
    tmp_path: Path,
) -> None:
    target = tmp_path / "repeat.txt"
    target.write_text("same\nmiddle\nsame\n", encoding="utf-8")

    with pytest.raises(PatchError, match="found 2") as failure:
        _apply(
            tmp_path,
            """*** Begin Patch
*** Update File: repeat.txt
@@
-same
+changed
*** End Patch""",
        )

    assert len(str(failure.value)) < 1_000
    assert target.read_text(encoding="utf-8") == "same\nmiddle\nsame\n"


def test_mid_write_failure_restores_every_touched_file(tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("one\n", encoding="utf-8")
    second.write_text("two\n", encoding="utf-8")
    calls = 0

    def fail_second(change: object) -> None:
        nonlocal calls
        calls += 1
        patching._commit_change(change)  # type: ignore[arg-type]
        if calls == 2:
            raise OSError("simulated disk failure")

    sandbox = SandboxRuntime(
        SandboxConfig(SandboxMode.DANGER_FULL_ACCESS, tmp_path, tmp_path)
    )
    with pytest.raises(RuntimeError, match="recovery complete"):
        apply_patch_text(
            """*** Begin Patch
*** Update File: first.txt
@@
-one
+changed-one
*** Update File: second.txt
@@
-two
+changed-two
*** End Patch""",
            sandbox_runtime=sandbox,
            commit_change=fail_second,
        )

    assert first.read_text(encoding="utf-8") == "one\n"
    assert second.read_text(encoding="utf-8") == "two\n"


def test_restricted_and_read_only_sandboxes_enforce_boundaries(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("before", encoding="utf-8")
    writable = SandboxRuntime(
        SandboxConfig(SandboxMode.WORKSPACE_WRITE, project, project),
        docker_executable="docker",
    )
    read_only = SandboxRuntime(
        SandboxConfig(SandboxMode.READ_ONLY, project, project),
        docker_executable="docker",
    )
    patch = "*** Begin Patch\n*** Add File: new.txt\n+x\n*** End Patch"

    assert "Applied patch" in apply_patch_text(patch, sandbox_runtime=writable)
    with pytest.raises(PermissionError, match="read-only"):
        apply_patch_text(
            "*** Begin Patch\n*** Add File: blocked.txt\n+x\n*** End Patch",
            sandbox_runtime=read_only,
        )
    with pytest.raises(PatchError, match="invalid"):
        apply_patch_text(
            "*** Begin Patch\n*** Add File: ../outside.txt\n+x\n*** End Patch",
            sandbox_runtime=writable,
        )
    assert outside.read_text(encoding="utf-8") == "before"


@pytest.mark.skipif(os.name == "nt", reason="symlink creation is restricted on Windows")
def test_patch_rejects_symbolic_link_target(tmp_path: Path) -> None:
    (tmp_path / "real.txt").write_text("before\n", encoding="utf-8")
    os.symlink("real.txt", tmp_path / "link.txt")
    with pytest.raises(PatchError, match="symbolic-link"):
        _apply(
            tmp_path,
            "*** Begin Patch\n*** Update File: link.txt\n@@\n-before\n+after\n*** End Patch",
        )


def test_registry_declares_recovery_paths_and_destructive_delete(tmp_path: Path) -> None:
    sandbox = SandboxRuntime(
        SandboxConfig(SandboxMode.DANGER_FULL_ACCESS, tmp_path, tmp_path)
    )
    registry = build_tool_registry(sandbox_runtime=sandbox)
    patch = """*** Begin Patch
*** Add File: a.txt
+a
*** Delete File: b.txt
*** End Patch"""

    assert registry.recovery_paths("apply_patch", {"patch": patch}) == (
        "a.txt",
        "b.txt",
    )
    assert registry.effect("apply_patch", {"patch": patch}) is ToolEffect.DESTRUCTIVE
