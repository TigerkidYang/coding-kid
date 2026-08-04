"""The small set of local tools available to the model."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Mapping

from coding_kid.background_tasks import BackgroundTaskManager
from coding_kid.events import CancellationToken
from coding_kid.terminal import run_command

ToolFunction = Callable[..., str]
ToolEntry = dict[str, Any]
MAX_SEARCH_RESULTS = 100
MAX_SEARCH_FILE_BYTES = 1_000_000
MAX_TOOL_OUTPUT_CHARS = 50_000
SKIPPED_SEARCH_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "node_modules",
}


def execute(
    command: str,
    background: bool = False,
    *,
    task_manager: BackgroundTaskManager | None = None,
) -> str:
    """Run one foreground command or explicitly start a background task."""
    if background:
        if task_manager is None:
            raise RuntimeError("Background task runtime is not active")
        return task_manager.start(command).model_text()
    return run_command(command).model_text()


def task(
    action: str,
    task_id: str | None = None,
    timeout_seconds: float = 10,
    *,
    task_manager: BackgroundTaskManager | None = None,
    cancellation_token: CancellationToken | None = None,
) -> str:
    """Inspect, wait for, or stop one process-local background task."""
    if task_manager is None:
        raise RuntimeError("Background task runtime is not active")
    if action == "list":
        return task_manager.status_text()
    if action not in {"poll", "wait", "stop"}:
        raise ValueError("action must be list, poll, wait, or stop")
    if not task_id:
        raise ValueError(f"task_id is required for {action}")
    if action == "poll":
        return task_manager.poll(task_id).model_text()
    if action == "stop":
        return task_manager.stop(task_id).model_text()
    snapshot, timed_out = task_manager.wait(
        task_id,
        timeout_seconds,
        cancellation_token,
    )
    return snapshot.model_text(wait_timed_out=timed_out)


def read(path: str) -> str:
    """Read a UTF-8 text file."""
    return Path(path).read_text(encoding="utf-8")


def write(path: str, content: str) -> str:
    """Create or completely overwrite a UTF-8 text file."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return f"Wrote {file_path}"


def search(query: str, path: str = ".") -> str:
    """Search file names and UTF-8 text contents below a path."""
    if not query:
        raise ValueError("search query must not be empty")

    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"Search path does not exist: {root}")

    matches: list[str] = []

    for file_path in _search_files(root):
        display_path = (
            file_path.name if root.is_file() else str(file_path.relative_to(root))
        )
        if query in file_path.name:
            matches.append(f"FILE {display_path}")
            if len(matches) == MAX_SEARCH_RESULTS:
                return _truncated_search_result(matches)

        try:
            if file_path.stat().st_size > MAX_SEARCH_FILE_BYTES:
                continue
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        for line_number, line in enumerate(lines, start=1):
            if query in line:
                matches.append(f"TEXT {display_path}:{line_number}:{line}")
                if len(matches) == MAX_SEARCH_RESULTS:
                    return _truncated_search_result(matches)

    return "\n".join(matches) if matches else "No matches found."


def _search_files(root: Path):
    """Yield files deterministically without descending into generated trees."""
    if root.is_file():
        yield root
        return

    for directory, directory_names, file_names in os.walk(root):
        directory_names[:] = sorted(
            name for name in directory_names if name not in SKIPPED_SEARCH_DIRECTORIES
        )
        for file_name in sorted(file_names):
            yield Path(directory) / file_name


def _truncated_search_result(matches: list[str]) -> str:
    """Mark a bounded search result so the model knows more matches exist."""
    matches.append(f"... search results truncated at {MAX_SEARCH_RESULTS} matches")
    return "\n".join(matches)


def patch(path: str, old_text: str, new_text: str) -> str:
    """Replace one unique, exact text fragment in a UTF-8 file."""
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    count = content.count(old_text)
    if count == 0:
        raise ValueError("old_text was not found")
    if count > 1:
        raise ValueError(f"old_text appears {count} times; make it unique")

    file_path.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
    return f"Patched {file_path}"


def delete(path: str) -> str:
    """Delete one file."""
    file_path = Path(path)
    file_path.unlink()
    return f"Deleted {file_path}"


VALID_TODO_STATUSES = {"pending", "in_progress", "completed"}
MAX_TODO_ITEMS = 20
MAX_TODO_CONTENT_CHARS = 200


class TodoState:
    """One Agent's isolated, replace-based checklist."""

    def __init__(self, items: list[dict[str, Any]] | None = None) -> None:
        self._items: list[dict[str, str]] = []
        if items is not None:
            self.replace(items)

    @property
    def items(self) -> list[dict[str, str]]:
        return [dict(item) for item in self._items]

    def replace(self, todos: list[dict[str, Any]]) -> None:
        self._items = _validate_todos(todos)

    def clear(self) -> None:
        self._items = []


_default_todo_state = TodoState()


def get_todos() -> list[dict[str, str]]:
    """Return a copy of the process-local todo checklist."""
    return _default_todo_state.items


def set_todos(todos: list[dict[str, Any]]) -> None:
    """Validate and replace the process-local todo checklist."""
    _default_todo_state.replace(todos)


def _validate_todos(todos: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not isinstance(todos, list):
        raise ValueError("todos must be a list")
    if len(todos) > MAX_TODO_ITEMS:
        raise ValueError(f"todos may contain at most {MAX_TODO_ITEMS} items")

    normalized: list[dict[str, str]] = []
    in_progress_count = 0
    for item in todos:
        if not isinstance(item, dict):
            raise ValueError("each todo must be an object")
        content = item.get("content")
        status = item.get("status")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("todo content must be a non-empty string")
        content = content.strip()
        if len(content) > MAX_TODO_CONTENT_CHARS:
            raise ValueError(
                f"todo content may contain at most {MAX_TODO_CONTENT_CHARS} characters"
            )
        if status not in VALID_TODO_STATUSES:
            raise ValueError("todo status must be pending, in_progress, or completed")
        if status == "in_progress":
            in_progress_count += 1
        normalized.append({"content": content, "status": status})

    if in_progress_count > 1:
        raise ValueError("at most one todo may be in_progress")

    return normalized


def clear_todos() -> None:
    """Clear the process-local todo checklist."""
    _default_todo_state.clear()


def format_todos(todos: list[dict[str, str]] | None = None) -> str:
    """Render a todo checklist for prompts and tool results."""
    items = _default_todo_state.items if todos is None else todos
    if not items:
        return "(no todos)"
    return "\n".join(
        f"{index}. [{item['status']}] {item['content']}"
        for index, item in enumerate(items, start=1)
    )


def todo(todos: list[dict[str, Any]]) -> str:
    """Replace the full session todo checklist."""
    set_todos(todos)
    if not todos:
        return "Cleared todos."
    return (
        "Updated todos:\n"
        f"{format_todos()}\n"
        "Continue from this list. Keep at most one item in_progress while "
        "working, and mark items completed when finished."
    )


# The registry is both the dispatch table and the source of model-visible tool
# definitions. Keeping it explicit makes the first version easy to inspect.
TOOLS: dict[str, ToolEntry] = {
    "execute": {
        "description": (
            "Run one non-interactive Windows PowerShell command in the current "
            "directory. Set background=true only when its result is not needed "
            "immediately. Foreground output is bounded and its process tree is "
            "terminated after 2 minutes. Background execution returns a task ID."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "minLength": 1},
                "background": {"type": "boolean", "default": False},
            },
            "required": ["command", "background"],
            "additionalProperties": False,
        },
        "function": execute,
    },
    "read": {
        "description": "Read a UTF-8 text file.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "minLength": 1}},
            "required": ["path"],
            "additionalProperties": False,
        },
        "function": read,
    },
    "write": {
        "description": "Create or completely overwrite a UTF-8 text file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        "function": write,
    },
    "search": {
        "description": (
            "Search for a literal non-empty substring in file names and text "
            "contents below a path. This is not a glob search."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "path": {"type": "string", "minLength": 1, "default": "."},
            },
            "required": ["query", "path"],
            "additionalProperties": False,
        },
        "function": search,
    },
    "patch": {
        "description": "Replace one unique, exact text fragment in a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "old_text": {"type": "string", "minLength": 1},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
            "additionalProperties": False,
        },
        "function": patch,
    },
    "delete": {
        "description": "Delete one file.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "minLength": 1}},
            "required": ["path"],
            "additionalProperties": False,
        },
        "function": delete,
    },
    "todo": {
        "description": (
            "Replace the full session task checklist. Use for multi-step work. "
            "Each item needs content and status "
            "(pending, in_progress, or completed). At most one item may be "
            "in_progress. Pass an empty list to clear a finished checklist."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "maxItems": MAX_TODO_ITEMS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": MAX_TODO_CONTENT_CHARS,
                            },
                            "status": {
                                "type": "string",
                                "enum": [
                                    "pending",
                                    "in_progress",
                                    "completed",
                                ],
                            },
                        },
                        "required": ["content", "status"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["todos"],
            "additionalProperties": False,
        },
        "function": todo,
    },
    "task": {
        "description": (
            "Manage process-local background shell tasks. list and poll return "
            "immediately; wait blocks for completion for at most 30 seconds; stop "
            "terminates the process tree. Waiting for completion does not prove a "
            "server is ready—inspect logs or run a concrete health probe."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "poll", "wait", "stop"],
                },
                "task_id": {"type": ["string", "null"], "minLength": 1},
                "timeout_seconds": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 30,
                    "default": 10,
                },
            },
            "required": ["action", "task_id", "timeout_seconds"],
            "additionalProperties": False,
        },
        "function": task,
    },
}


class ToolRegistry:
    """An immutable-at-call-sites session-owned tool snapshot."""

    def __init__(self, entries: Mapping[str, ToolEntry] | None = None) -> None:
        self._entries = dict(TOOLS if entries is None else entries)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def with_tool(self, name: str, entry: ToolEntry) -> ToolRegistry:
        if name in self._entries:
            raise ValueError(f"Duplicate tool name: {name}")
        entries = dict(self._entries)
        entries[name] = entry
        return ToolRegistry(entries)

    def definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": name,
                "description": entry["description"],
                "parameters": entry["parameters"],
                "strict": entry.get("strict", True),
            }
            for name, entry in self._entries.items()
        ]

    def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        entry = self._entries.get(name)
        if entry is None:
            return f"ERROR: Unknown tool: {name}"
        function: ToolFunction = entry["function"]
        try:
            result = function(**arguments)
        except Exception as error:  # The model needs the error so it can recover.
            result = f"ERROR: {type(error).__name__}: {error}"
        return _bounded_tool_output(result)


DEFAULT_TOOL_REGISTRY = ToolRegistry()


def build_tool_registry(
    task_manager: BackgroundTaskManager | None = None,
    cancellation_token: CancellationToken | None = None,
    todo_state: TodoState | None = None,
) -> ToolRegistry:
    """Bind process-local task state to one immutable per-turn registry."""
    if task_manager is None and todo_state is None:
        return DEFAULT_TOOL_REGISTRY
    entries = {name: dict(entry) for name, entry in TOOLS.items()}
    if todo_state is not None:
        entries["todo"]["function"] = lambda todos: _todo_for_state(todo_state, todos)
    if task_manager is not None:
        entries["execute"]["function"] = lambda command, background=False: execute(
            command,
            background,
            task_manager=task_manager,
        )
        entries["task"]["function"] = lambda action, task_id=None, timeout_seconds=10: (
            task(
                action,
                task_id,
                timeout_seconds,
                task_manager=task_manager,
                cancellation_token=cancellation_token,
            )
        )
    return ToolRegistry(entries)


def _todo_for_state(state: TodoState, todos: list[dict[str, Any]]) -> str:
    state.replace(todos)
    if not todos:
        return "Cleared todos."
    return (
        "Updated todos:\n"
        f"{format_todos(state.items)}\n"
        "Continue from this list. Keep at most one item in_progress while "
        "working, and mark items completed when finished."
    )


def tool_definitions() -> list[dict[str, Any]]:
    """Build the tool definitions sent to the model."""
    return DEFAULT_TOOL_REGISTRY.definitions()


def dispatch_tool(name: str, arguments: dict[str, Any]) -> str:
    """Call a registered tool and turn failures into model-readable text."""
    return DEFAULT_TOOL_REGISTRY.dispatch(name, arguments)


def _bounded_tool_output(result: str) -> str:
    """Keep any single tool result from overwhelming the next model request."""
    if len(result) <= MAX_TOOL_OUTPUT_CHARS:
        return result

    half = MAX_TOOL_OUTPUT_CHARS // 2
    omitted = len(result) - (half * 2)
    marker = f"\n... tool output truncated ({omitted} characters omitted) ...\n"
    return f"{result[:half]}{marker}{result[-half:]}"
