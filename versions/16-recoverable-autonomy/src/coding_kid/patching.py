"""Bounded, provider-neutral multi-file patch parsing and application."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
from typing import Callable

from coding_kid.sandbox import SandboxRuntime


MAX_PATCH_CHARS = 200_000
MAX_PATCH_FILES = 50
MAX_PATCH_FILE_BYTES = 2_000_000
MAX_PATCH_CHANGED_CHARS = 500_000
MAX_PATCH_DIAGNOSTIC_CHARS = 800
PROTECTED_NAMES = {".git", ".coding-kid"}


class PatchError(ValueError):
    """A complete patch was rejected before any project bytes changed."""


@dataclass(frozen=True)
class Hunk:
    lines: tuple[str, ...]


@dataclass(frozen=True)
class FilePatch:
    action: str
    path: str
    hunks: tuple[Hunk, ...] = ()
    added_lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Change:
    action: str
    path: Path
    display_path: str
    before: bytes | None
    after: bytes | None
    mode: int | None


def patch_paths(patch: str) -> tuple[str, ...]:
    """Return validated file targets for recovery coverage."""
    return tuple(item.path for item in parse_patch(patch))


def patch_is_destructive(patch: str) -> bool:
    """Classify malformed patches conservatively and deletes as destructive."""
    try:
        return any(item.action == "delete" for item in parse_patch(patch))
    except (PatchError, TypeError):
        return True


def parse_patch(patch: str) -> tuple[FilePatch, ...]:
    """Parse the supported Codex-style envelope without touching the filesystem."""
    if not isinstance(patch, str):
        raise PatchError("patch must be a string")
    if len(patch) > MAX_PATCH_CHARS:
        raise PatchError(f"patch exceeds {MAX_PATCH_CHARS} characters")
    lines = patch.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines or lines[0] != "*** Begin Patch":
        raise PatchError("line 1: expected *** Begin Patch")
    index = 1
    files: list[FilePatch] = []
    seen: set[str] = set()
    while index < len(lines) and lines[index] != "*** End Patch":
        header = lines[index]
        actions = {
            "*** Add File: ": "add",
            "*** Update File: ": "update",
            "*** Delete File: ": "delete",
        }
        matched = next((item for item in actions if header.startswith(item)), None)
        if matched is None:
            raise PatchError(f"line {index + 1}: invalid file marker {header!r}")
        action = actions[matched]
        path = header.removeprefix(matched)
        _validate_patch_path_text(path)
        canonical = path.replace("\\", "/")
        if canonical in seen:
            raise PatchError(f"line {index + 1}: duplicate path {path}")
        seen.add(canonical)
        index += 1
        body: list[str] = []
        while index < len(lines) and not lines[index].startswith("*** "):
            body.append(lines[index])
            index += 1
        if action == "add":
            if any(not line.startswith("+") for line in body):
                raise PatchError(f"{path}: added file lines must start with +")
            files.append(
                FilePatch(action, path, added_lines=tuple(line[1:] for line in body))
            )
        elif action == "delete":
            if body:
                raise PatchError(f"{path}: delete marker must not contain hunks")
            files.append(FilePatch(action, path))
        else:
            hunks: list[Hunk] = []
            cursor = 0
            while cursor < len(body):
                if not body[cursor].startswith("@@"):
                    raise PatchError(f"{path}: expected @@ hunk marker")
                cursor += 1
                hunk_lines: list[str] = []
                while cursor < len(body) and not body[cursor].startswith("@@"):
                    line = body[cursor]
                    if not line or line[0] not in {" ", "+", "-"}:
                        raise PatchError(
                            f"{path}: hunk lines must start with space, +, or -"
                        )
                    hunk_lines.append(line)
                    cursor += 1
                if not hunk_lines:
                    raise PatchError(f"{path}: hunk must not be empty")
                hunks.append(Hunk(tuple(hunk_lines)))
            if not hunks:
                raise PatchError(f"{path}: update requires at least one hunk")
            files.append(FilePatch(action, path, tuple(hunks)))
        if len(files) > MAX_PATCH_FILES:
            raise PatchError(f"patch exceeds {MAX_PATCH_FILES} files")
    if index >= len(lines) or lines[index] != "*** End Patch":
        raise PatchError("missing *** End Patch")
    if any(line for line in lines[index + 1 :]):
        raise PatchError("content after *** End Patch is not allowed")
    if not files:
        raise PatchError("patch contains no file changes")
    return tuple(files)


def apply_patch_text(
    patch: str,
    *,
    sandbox_runtime: SandboxRuntime | None = None,
    commit_change: Callable[[_Change], None] | None = None,
) -> str:
    """Validate every change, then apply it with call-local recovery on I/O failure."""
    parsed = parse_patch(patch)
    changes: list[_Change] = []
    changed_chars = 0
    for item in parsed:
        target = _resolve_target(item.path, sandbox_runtime)
        if target.is_symlink() or any(parent.is_symlink() for parent in target.parents):
            raise PatchError(f"{item.path}: symbolic-link targets are not supported")
        before: bytes | None
        mode: int | None
        if target.exists():
            if not target.is_file():
                raise PatchError(f"{item.path}: target is not a regular file")
            before = target.read_bytes()
            mode = stat.S_IMODE(target.stat().st_mode)
            if len(before) > MAX_PATCH_FILE_BYTES:
                raise PatchError(
                    f"{item.path}: file exceeds {MAX_PATCH_FILE_BYTES} bytes"
                )
        else:
            before = None
            mode = None
        if item.action == "add":
            if before is not None:
                raise PatchError(f"{item.path}: add target already exists")
            text = "\n".join(item.added_lines)
            if item.added_lines:
                text += "\n"
            after = text.encode("utf-8")
        elif item.action == "delete":
            if before is None:
                raise PatchError(f"{item.path}: delete target does not exist")
            after = None
        else:
            if before is None:
                raise PatchError(f"{item.path}: update target does not exist")
            try:
                original = before.decode("utf-8")
            except UnicodeDecodeError as error:
                raise PatchError(f"{item.path}: target is not UTF-8 text") from error
            newline = _newline_style(original)
            normalized = original.replace("\r\n", "\n").replace("\r", "\n")
            updated = _apply_hunks(item.path, normalized, item.hunks)
            if newline != "\n":
                updated = updated.replace("\n", newline)
            after = updated.encode("utf-8")
        if after is not None and len(after) > MAX_PATCH_FILE_BYTES:
            raise PatchError(
                f"{item.path}: result exceeds {MAX_PATCH_FILE_BYTES} bytes"
            )
        changed_chars += max(len(before or b""), len(after or b""))
        if changed_chars > MAX_PATCH_CHANGED_CHARS:
            raise PatchError(
                f"patch exceeds the {MAX_PATCH_CHANGED_CHARS}-character change budget"
            )
        changes.append(_Change(item.action, target, item.path, before, after, mode))

    writer = commit_change or _commit_change
    completed: list[_Change] = []
    try:
        for change in changes:
            writer(change)
            completed.append(change)
    except BaseException as error:
        restored: list[str] = []
        restore_errors: list[str] = []
        for change in reversed((*completed, changes[len(completed)])):
            try:
                _restore_change(change)
                restored.append(change.display_path)
            except BaseException as restore_error:  # noqa: BLE001
                restore_errors.append(
                    f"{change.display_path}: {type(restore_error).__name__}: {restore_error}"
                )
        status = (
            "recovery complete"
            if not restore_errors
            else "recovery incomplete: " + "; ".join(restore_errors)
        )
        raise RuntimeError(
            f"write failed at {changes[len(completed)].display_path}: "
            f"{type(error).__name__}: {error}; {status}"
        ) from error
    summary = ", ".join(f"{item.action} {item.path}" for item in parsed)
    return f"Applied patch to {len(parsed)} file(s): {summary}"


def _apply_hunks(path: str, content: str, hunks: tuple[Hunk, ...]) -> str:
    lines = content.splitlines(keepends=True)
    cursor = 0
    for number, hunk in enumerate(hunks, start=1):
        before = [line[1:] + "\n" for line in hunk.lines if line[0] in {" ", "-"}]
        after = [line[1:] + "\n" for line in hunk.lines if line[0] in {" ", "+"}]
        if before and content and not content.endswith("\n"):
            before[-1] = before[-1].removesuffix("\n")
        positions = [
            index
            for index in range(cursor, len(lines) - len(before) + 1)
            if lines[index : index + len(before)] == before
        ]
        if not before:
            positions = [cursor]
        if len(positions) != 1:
            diagnostic = _bounded_context(content, before)
            raise PatchError(
                f"{path}: hunk {number} expected one context match, found "
                f"{len(positions)}. Nearby context: {diagnostic}"
            )
        position = positions[0]
        if before and before[-1] and not before[-1].endswith("\n") and after:
            after[-1] = after[-1].removesuffix("\n")
        lines[position : position + len(before)] = after
        cursor = position + len(after)
    return "".join(lines)


def _bounded_context(content: str, before: list[str]) -> str:
    needle = next((line.strip() for line in before if line.strip()), "")
    position = content.find(needle[:80]) if needle else 0
    if position < 0:
        position = 0
    start = max(0, position - MAX_PATCH_DIAGNOSTIC_CHARS // 2)
    excerpt = content[start : start + MAX_PATCH_DIAGNOSTIC_CHARS]
    return repr(excerpt)


def _validate_patch_path_text(path: str) -> None:
    candidate = Path(path)
    if not path or candidate.is_absolute() or ":" in path:
        raise PatchError(f"invalid project-relative path: {path!r}")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise PatchError(f"invalid project-relative path: {path!r}")
    if any(part.casefold() in PROTECTED_NAMES for part in candidate.parts):
        raise PatchError(f"protected project metadata path: {path}")


def _resolve_target(path: str, sandbox_runtime: SandboxRuntime | None) -> Path:
    _validate_patch_path_text(path)
    root = (
        sandbox_runtime.config.project_root
        if sandbox_runtime is not None
        else Path.cwd().resolve()
    )
    base = sandbox_runtime.config.cwd if sandbox_runtime is not None else Path.cwd()
    lexical = Path(os.path.abspath(base / path))
    if sandbox_runtime is not None:
        sandbox_runtime.resolve_path(path, write=True)
    resolved = lexical.resolve(strict=False)
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise PatchError(f"path escapes project: {path}") from error
    return lexical


def _newline_style(text: str) -> str:
    return (
        "\r\n" if text.count("\r\n") > text.count("\n") - text.count("\r\n") else "\n"
    )


def _commit_change(change: _Change) -> None:
    if change.after is None:
        change.path.unlink()
        return
    change.path.parent.mkdir(parents=True, exist_ok=True)
    temporary = change.path.with_name(
        f".{change.path.name}.coding-kid-patch-{os.getpid()}"
    )
    try:
        temporary.write_bytes(change.after)
        if change.mode is not None:
            os.chmod(temporary, change.mode)
        os.replace(temporary, change.path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _restore_change(change: _Change) -> None:
    if change.before is None:
        if change.path.exists() or change.path.is_symlink():
            change.path.unlink()
        return
    change.path.parent.mkdir(parents=True, exist_ok=True)
    change.path.write_bytes(change.before)
    if change.mode is not None:
        os.chmod(change.path, change.mode)
