"""Build the stable and dynamic context sent with each model request."""

from __future__ import annotations

import os
import platform
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_INSTRUCTIONS_MAX_BYTES = 32 * 1024
PROJECT_INSTRUCTIONS_FILENAME = "AGENTS.md"
PROJECT_CONTEXT_HEADER = """Project instructions are provided below.
They come from AGENTS.md files in the current project, ordered from the project
root toward the current working directory. Follow the more specific later
instructions when project instructions conflict."""

BASE_INSTRUCTIONS = """You are Coding Kid, a coding agent working in the current directory.
Only call the tools provided in the current request. Never invent tool names.
Use the available tools to inspect, change, and verify code when needed.
Read or search before changing code you have not inspected.
Use "." for the current directory; never send an empty path or search query.
Use the fewest tool calls needed and stop gathering once you can answer.
For repository overviews, inspect only the top level, README, project configuration,
one relevant architecture/context document, and source/test file names. Do not read
every file, run tests, inspect Git state or diffs, inspect version archives, run
recursive tree commands, or inspect virtual environments, caches, or dependencies
unless the user specifically asks.
For tasks with three or more distinct steps, use the todo tool to list the steps
before making changes. Keep at most one item in_progress. Update the list as you
finish each step. Skip the todo tool for simple one-step requests.
After using tools, always answer the user with the useful result. Never finish
with only internal reasoning or an empty response.
Use execute with background=true only when its result is not needed immediately.
Use the task tool to list, poll, wait for, or stop background work. A started
process is not proof that a server is ready: inspect its output or run a concrete
health probe. Do not busy-poll or use repeated sleep commands while waiting.
Use spawn_agent only for concrete, independent subtasks that can usefully run in
parallel. Each child prompt must be self-contained because children cannot see
this conversation. Child Agents share the working directory: never delegate
overlapping writes concurrently. Use agent to inspect, wait, continue, or stop
them, and verify their evidence before synthesizing a result.
When the task is complete, explain the result clearly and briefly."""


@dataclass(frozen=True)
class ProjectInstruction:
    """One bounded project instruction file and its source."""

    path: Path
    content: str
    truncated: bool = False


@dataclass(frozen=True)
class SessionContext:
    """Immutable environment and project context captured for one chat."""

    cwd: Path
    operating_system: str
    shell: str
    model: str
    local_date: str
    project_root: Path
    project_instructions: tuple[ProjectInstruction, ...]
    project_instructions_truncated: bool = False

    @classmethod
    def capture(cls, cwd: Path | str | None = None) -> SessionContext:
        """Capture runtime facts and bounded project instructions once."""
        resolved_cwd = Path.cwd().resolve() if cwd is None else Path(cwd).resolve()
        project_root = find_project_root(resolved_cwd)
        instructions, truncated = load_project_instructions(
            project_root,
            resolved_cwd,
        )
        return cls(
            cwd=resolved_cwd,
            operating_system=f"{platform.system()} {platform.release()}".strip(),
            shell="PowerShell",
            model=os.getenv("OPENROUTER_MODEL", "not set"),
            local_date=date.today().isoformat(),
            project_root=project_root,
            project_instructions=instructions,
            project_instructions_truncated=truncated,
        )


def find_project_root(cwd: Path) -> Path:
    """Return the nearest ancestor with a .git marker, or cwd when absent."""
    resolved = cwd.resolve()
    for directory in (resolved, *resolved.parents):
        if (directory / ".git").exists():
            return directory
    return resolved


def directories_from_root(project_root: Path, cwd: Path) -> tuple[Path, ...]:
    """List directories from project root through cwd, inclusive."""
    root = project_root.resolve()
    current = cwd.resolve()
    try:
        relative = current.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{current} is not inside project root {root}") from error

    directories = [root]
    cursor = root
    for part in relative.parts:
        cursor /= part
        directories.append(cursor)
    return tuple(directories)


def load_project_instructions(
    project_root: Path,
    cwd: Path,
    *,
    max_bytes: int = PROJECT_INSTRUCTIONS_MAX_BYTES,
) -> tuple[tuple[ProjectInstruction, ...], bool]:
    """Load root-to-cwd AGENTS.md files within one shared byte budget."""
    if max_bytes < 0:
        raise ValueError("max_bytes must not be negative")

    loaded: list[ProjectInstruction] = []
    remaining = max_bytes
    truncated_any = False

    for directory in directories_from_root(project_root, cwd):
        path = directory / PROJECT_INSTRUCTIONS_FILENAME
        try:
            metadata = path.stat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise RuntimeError(
                f"Could not inspect project instructions at {path}: {error}"
            ) from error
        if not stat.S_ISREG(metadata.st_mode):
            continue

        if remaining == 0:
            truncated_any = True
            continue

        try:
            data = path.read_bytes()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise RuntimeError(
                f"Could not load project instructions from {path}: {error}"
            ) from error

        text = data.decode("utf-8", errors="replace")
        if not text.strip():
            continue

        truncated = len(data) > remaining
        included = data[:remaining] if truncated else data
        loaded.append(
            ProjectInstruction(
                path=path.resolve(),
                content=included.decode("utf-8", errors="replace"),
                truncated=truncated,
            )
        )
        remaining -= len(included)
        truncated_any = truncated_any or truncated

    return tuple(loaded), truncated_any


def render_environment(context: SessionContext) -> str:
    """Render the stable runtime portion of model instructions."""
    return "\n".join(
        [
            "Runtime environment:",
            f"- Current working directory: {context.cwd}",
            f"- Project root: {context.project_root}",
            f"- Operating system: {context.operating_system}",
            "- Shell: PowerShell",
            f"- Configured model (OPENROUTER_MODEL): {context.model}",
            f"- Session date: {context.local_date}",
            "The execute tool runs non-interactive Windows PowerShell commands.",
        ]
    )


def render_project_instructions(context: SessionContext) -> str | None:
    """Render source-labeled project instructions as contextual user input."""
    if not context.project_instructions:
        return None

    sections = [PROJECT_CONTEXT_HEADER]
    for instruction in context.project_instructions:
        content = instruction.content.rstrip()
        if instruction.truncated:
            content = (
                f"{content}\n\n"
                f"[Truncated at the {PROJECT_INSTRUCTIONS_MAX_BYTES}-byte "
                "project-instruction budget.]"
            )
        sections.append(f"## {instruction.path}\n\n{content}")
    if (
        context.project_instructions_truncated
        and not context.project_instructions[-1].truncated
    ):
        sections.append(
            "[Additional AGENTS.md content was omitted because the shared "
            f"{PROJECT_INSTRUCTIONS_MAX_BYTES}-byte budget was exhausted.]"
        )
    return "\n\n".join(sections)


def build_instructions(
    context: SessionContext,
    todos: Sequence[Mapping[str, str]],
    overlays: Sequence[str] = (),
    *,
    base_instructions: str = BASE_INSTRUCTIONS,
) -> str:
    """Combine stable instructions with current todo and recovery suffixes."""
    sections = [base_instructions, render_environment(context)]
    if todos:
        rendered_todos = "\n".join(
            f"- [{item['status']}] {item['content']}" for item in todos
        )
        sections.append(f"Current todos:\n{rendered_todos}")
    sections.extend(overlay.strip() for overlay in overlays if overlay.strip())
    return "\n\n".join(sections)


def build_model_input(context: SessionContext, messages: Sequence[Any]) -> list[Any]:
    """Prepend cached project context without mutating conversation history."""
    project_context = render_project_instructions(context)
    if not project_context:
        return list(messages)
    return [
        {"role": "user", "content": project_context},
        *messages,
    ]
