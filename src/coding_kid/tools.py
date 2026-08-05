"""The small set of local tools available to the model."""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any, Callable, Mapping, TYPE_CHECKING

from coding_kid.background_tasks import BackgroundTaskManager
from coding_kid.events import CancellationToken, TurnCancelled
from coding_kid.permissions import PermissionBroker, ToolEffect
from coding_kid.sandbox import SandboxRuntime, SandboxViolation
from coding_kid.terminal import run_command
from coding_kid.workflow import CollaborationMode
from coding_kid.web import WebRuntime

if TYPE_CHECKING:
    from coding_kid.agents import AgentManager

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
    interactive: bool = False,
    yield_time_ms: int = 10_000,
    reason: str | None = None,
    *,
    task_manager: BackgroundTaskManager | None = None,
    cancellation_token: CancellationToken | None = None,
    sandbox_runtime: SandboxRuntime | None = None,
) -> str:
    """Run a short command or yield one continuing execution session."""
    del reason
    if not isinstance(yield_time_ms, int) or not 0 <= yield_time_ms <= 30_000:
        raise ValueError("yield_time_ms must be an integer between 0 and 30000")
    if task_manager is not None:
        started = task_manager.start(command, interactive=interactive)
        if background:
            return started.model_text()
        try:
            snapshot, _ = task_manager.wait(
                started.task_id,
                yield_time_ms / 1000,
                cancellation_token,
                incremental=True,
            )
        except TurnCancelled:
            snapshot = task_manager.settle(started.task_id)
            return (
                snapshot.model_text(wait_timed_out=snapshot.status == "running")
                + "\nturn_interrupted: true\n"
                "The execution session was retained; inspect or stop it later."
            )
        return snapshot.model_text(wait_timed_out=snapshot.status == "running")
    if background or interactive:
        raise RuntimeError("Execution-session runtime is not active")
    return run_command(
        command,
        cancellation_token=cancellation_token,
        sandbox_runtime=sandbox_runtime,
    ).model_text()


def task(
    action: str,
    task_id: str | None = None,
    timeout_seconds: float = 10,
    input: str | None = None,
    submit: bool = True,
    command: str | None = None,
    reason: str | None = None,
    *,
    task_manager: BackgroundTaskManager | None = None,
    cancellation_token: CancellationToken | None = None,
) -> str:
    """Inspect or continue one process-local execution session."""
    del reason
    if task_manager is None:
        raise RuntimeError("Execution-session runtime is not active")
    if action == "list":
        return task_manager.status_text()
    if action not in {"poll", "wait", "write", "interrupt", "stop", "check"}:
        raise ValueError(
            "action must be list, poll, wait, write, interrupt, stop, or check"
        )
    if not task_id:
        raise ValueError(f"task_id is required for {action}")
    if action == "poll":
        return task_manager.poll(task_id, incremental=True).model_text()
    if action == "write":
        if input is None:
            raise ValueError("input is required for write")
        return task_manager.write(task_id, input, submit=submit).model_text()
    if action == "interrupt":
        return task_manager.interrupt(task_id).model_text()
    if action == "check":
        if not command:
            raise ValueError("command is required for check")
        return (
            "readiness_check: explicit\n"
            + task_manager.check(
                task_id,
                command,
                timeout_seconds,
                cancellation_token,
            ).model_text()
        )
    if action == "stop":
        return task_manager.stop(task_id).model_text()
    snapshot, timed_out = task_manager.wait(
        task_id,
        timeout_seconds,
        cancellation_token,
        incremental=True,
    )
    return snapshot.model_text(wait_timed_out=timed_out)


def spawn_agent(
    description: str,
    prompt: str,
    isolation: str = "worktree",
    fork_turns: int = 0,
    *,
    agent_manager: AgentManager | None = None,
) -> str:
    """Start one process-local child Agent, isolated by default."""
    if agent_manager is None:
        raise RuntimeError("Child Agent runtime is not active")
    return agent_manager.start(
        description,
        prompt,
        isolation=isolation,
        fork_turns=fork_turns,
    ).model_text()


def agent(
    action: str,
    agent_id: str | None,
    message: str | None,
    timeout_seconds: float,
    confirm_discard: bool = False,
    *,
    agent_manager: AgentManager | None = None,
    cancellation_token: CancellationToken | None = None,
) -> str:
    """Inspect, wait for, continue, or stop a process-local child Agent."""
    if agent_manager is None:
        raise RuntimeError("Child Agent runtime is not active")
    if action == "list":
        if agent_id is not None or message is not None:
            raise ValueError("agent_id and message must be null for list")
        return agent_manager.status_text()
    valid_actions = {
        "poll",
        "wait",
        "followup",
        "stop",
        "diff",
        "integrate",
        "reconcile",
        "discard",
    }
    if action not in valid_actions:
        raise ValueError("unknown Agent action")
    if not agent_id:
        raise ValueError(f"agent_id is required for {action}")
    if action != "followup" and message is not None:
        raise ValueError(f"message must be null for {action}")
    if action == "poll":
        return agent_manager.poll(agent_id).model_text()
    if action == "followup":
        if not message:
            raise ValueError("message is required for followup")
        return agent_manager.followup(agent_id, message).model_text()
    if action == "diff":
        return agent_manager.diff(agent_id)
    if action == "integrate":
        return agent_manager.integrate(agent_id).model_text()
    if action == "reconcile":
        return agent_manager.reconcile(agent_id).model_text()
    if action == "discard":
        return agent_manager.discard(
            agent_id, confirmed=confirm_discard
        ).model_text()
    if action == "stop":
        return agent_manager.stop(agent_id, timeout_seconds).model_text()
    snapshot, timed_out = agent_manager.wait(
        agent_id, timeout_seconds, cancellation_token
    )
    return snapshot.model_text(wait_timed_out=timed_out)


def web_search(
    query: str,
    count: int = 5,
    *,
    web_runtime: WebRuntime | None = None,
    cancellation_token: CancellationToken | None = None,
) -> str:
    """Search the public web through the configured Brave API."""
    if web_runtime is None:
        raise RuntimeError("Web research runtime is not active")
    return web_runtime.search(query, count, cancellation_token)


def web_fetch(
    url: str,
    *,
    web_runtime: WebRuntime | None = None,
    cancellation_token: CancellationToken | None = None,
) -> str:
    """Fetch bounded text from one public HTTP(S) URL."""
    if web_runtime is None:
        raise RuntimeError("Web research runtime is not active")
    return web_runtime.fetch(url, cancellation_token)


def read(path: str, *, sandbox_runtime: SandboxRuntime | None = None) -> str:
    """Read a UTF-8 text file."""
    file_path = _tool_path(path, sandbox_runtime)
    return file_path.read_text(encoding="utf-8")


def write(
    path: str,
    content: str,
    *,
    sandbox_runtime: SandboxRuntime | None = None,
) -> str:
    """Create or completely overwrite a UTF-8 text file."""
    file_path = _tool_path(path, sandbox_runtime, write=True)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return f"Wrote {file_path}"


def search(
    query: str,
    path: str = ".",
    *,
    sandbox_runtime: SandboxRuntime | None = None,
) -> str:
    """Search file names and UTF-8 text contents below a path."""
    if not query:
        raise ValueError("search query must not be empty")

    root = _tool_path(path or ".", sandbox_runtime)
    if not root.exists():
        raise FileNotFoundError(f"Search path does not exist: {root}")

    matches: list[str] = []

    for file_path in _search_files(root):
        if sandbox_runtime is not None:
            try:
                file_path = sandbox_runtime.resolve_path(str(file_path))
            except SandboxViolation:
                continue
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


def patch(
    path: str,
    old_text: str,
    new_text: str,
    *,
    sandbox_runtime: SandboxRuntime | None = None,
) -> str:
    """Replace one unique, exact text fragment in a UTF-8 file."""
    file_path = _tool_path(path, sandbox_runtime, write=True)
    content = file_path.read_text(encoding="utf-8")
    count = content.count(old_text)
    if count == 0:
        raise ValueError("old_text was not found")
    if count > 1:
        raise ValueError(f"old_text appears {count} times; make it unique")

    file_path.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
    return f"Patched {file_path}"


def delete(path: str, *, sandbox_runtime: SandboxRuntime | None = None) -> str:
    """Delete one file."""
    file_path = _tool_path(path, sandbox_runtime, write=True)
    file_path.unlink()
    return f"Deleted {file_path}"


def _tool_path(
    path: str,
    sandbox_runtime: SandboxRuntime | None,
    *,
    write: bool = False,
) -> Path:
    if sandbox_runtime is None:
        return Path(path)
    return sandbox_runtime.resolve_path(path, write=write)


def _require_web_network(sandbox_runtime: SandboxRuntime | None) -> None:
    if (
        sandbox_runtime is not None
        and sandbox_runtime.restricted
        and not sandbox_runtime.config.network_enabled
    ):
        raise RuntimeError(
            "Web research is disabled by the startup sandbox network policy"
        )


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
        "effect": ToolEffect.COMMAND,
        "description": (
            "Run a command in the current project. Short commands return their "
            "result; a command still alive after yield_time_ms returns a stable "
            "task ID without restarting. Set interactive=true for a real terminal "
            "that can accept later task(write/interrupt) calls. background=true "
            "returns immediately. Running does not prove service readiness."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "minLength": 1},
                "background": {"type": "boolean", "default": False},
                "interactive": {"type": "boolean", "default": False},
                "yield_time_ms": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 30_000,
                    "default": 10_000,
                },
                "reason": {"type": ["string", "null"], "default": None},
            },
            "required": [
                "command",
                "background",
                "interactive",
                "yield_time_ms",
                "reason",
            ],
            "additionalProperties": False,
        },
        "function": execute,
        "hard_check": lambda arguments: _protect_command(arguments["command"]),
    },
    "read": {
        "effect": ToolEffect.READ_ONLY,
        "description": "Read a UTF-8 text file.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "minLength": 1}},
            "required": ["path"],
            "additionalProperties": False,
        },
        "function": read,
        "parallel_safe": True,
    },
    "write": {
        "effect": ToolEffect.PROJECT_WRITE,
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
        "effect": ToolEffect.READ_ONLY,
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
        "parallel_safe": True,
    },
    "patch": {
        "effect": ToolEffect.PROJECT_WRITE,
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
        "effect": ToolEffect.DESTRUCTIVE,
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
        "effect": ToolEffect.CONTROL,
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
    "spawn_agent": {
        "effect": ToolEffect.EXTERNAL,
        "description": (
            "Start an independent child Agent for one concrete, self-contained "
            "subtask. By default it runs asynchronously in an application-owned "
            "Git worktree; use shared isolation only when concurrent writes are "
            "intentionally safe. A bounded number of visible conversation turns "
            "may be forked without tool calls or hidden reasoning."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 120,
                },
                "prompt": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 12_000,
                },
                "isolation": {
                    "type": "string",
                    "enum": ["worktree", "shared"],
                    "default": "worktree",
                },
                "fork_turns": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 8,
                    "default": 0,
                },
            },
            "required": ["description", "prompt", "isolation", "fork_turns"],
            "additionalProperties": False,
        },
        "function": spawn_agent,
    },
    "agent": {
        "effect": lambda arguments: (
            ToolEffect.READ_ONLY
            if arguments.get("action") in {"list", "poll", "wait", "diff"}
            else ToolEffect.DESTRUCTIVE
            if arguments.get("action") in {"integrate", "reconcile", "discard"}
            else ToolEffect.EXTERNAL
        ),
        "description": (
            "Manage process-local child Agents. list and poll return immediately; "
            "wait blocks for at most 30 seconds; diff reviews isolated changes; "
            "integrate applies them into the current stage checkpoint; reconcile "
            "rebases a conflicting workspace onto current root changes; discard "
            "requires explicit confirmation. followup and stop retain their "
            "bounded lifecycle semantics."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "list",
                        "poll",
                        "wait",
                        "followup",
                        "stop",
                        "diff",
                        "integrate",
                        "reconcile",
                        "discard",
                    ],
                },
                "agent_id": {"type": ["string", "null"], "minLength": 1},
                "message": {
                    "type": ["string", "null"],
                    "minLength": 1,
                    "maxLength": 12_000,
                },
                "timeout_seconds": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 30,
                    "default": 10,
                },
                "confirm_discard": {"type": "boolean", "default": False},
            },
            "required": [
                "action",
                "agent_id",
                "message",
                "timeout_seconds",
                "confirm_discard",
            ],
            "additionalProperties": False,
        },
        "function": agent,
    },
    "web_search": {
        "effect": ToolEffect.EXTERNAL,
        "description": (
            "Search the public web with Brave Search. Returns bounded titles, "
            "snippets, numbered source URLs, and explicit untrusted-content "
            "provenance. Requires BRAVE_SEARCH_API_KEY."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 400},
                "count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                },
            },
            "required": ["query", "count"],
            "additionalProperties": False,
        },
        "function": web_search,
    },
    "web_fetch": {
        "effect": ToolEffect.EXTERNAL,
        "description": (
            "Fetch bounded public text from one HTTP(S) URL. Redirects are "
            "revalidated; private, local, credentialed, nonstandard-port, binary, "
            "oversized, and encoded responses are blocked."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "minLength": 1, "maxLength": 2048}
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        "function": web_fetch,
    },
    "task": {
        "effect": lambda arguments: (
            ToolEffect.READ_ONLY
            if arguments.get("action") in {"list", "poll", "wait"}
            else ToolEffect.COMMAND
            if arguments.get("action") in {"write", "check"}
            else ToolEffect.DESTRUCTIVE
        ),
        "description": (
            "Manage process-local execution sessions. poll/wait return only new "
            "output; write submits input to an interactive terminal; interrupt "
            "sends Ctrl+C while preserving the session when possible; stop ends "
            "the process tree; check runs an explicit bounded readiness command "
            "in the same host or container environment."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "list",
                        "poll",
                        "wait",
                        "write",
                        "interrupt",
                        "stop",
                        "check",
                    ],
                },
                "task_id": {"type": ["string", "null"], "minLength": 1},
                "input": {
                    "type": ["string", "null"],
                    "maxLength": 20_000,
                    "default": None,
                },
                "submit": {"type": "boolean", "default": True},
                "command": {
                    "type": ["string", "null"],
                    "minLength": 1,
                    "default": None,
                },
                "timeout_seconds": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 30,
                    "default": 10,
                },
                "reason": {"type": ["string", "null"], "default": None},
            },
            "required": [
                "action",
                "task_id",
                "input",
                "submit",
                "command",
                "timeout_seconds",
                "reason",
            ],
            "additionalProperties": False,
        },
        "function": task,
        "hard_check": lambda arguments: (
            _protect_command(
                arguments["input"]
                if arguments.get("action") == "write"
                else arguments["command"]
            )
            if arguments.get("action") in {"write", "check"}
            and (arguments.get("input") or arguments.get("command"))
            else None
        ),
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

    def definitions(
        self, *, allowed_effects: set[ToolEffect] | None = None
    ) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": name,
                "description": entry["description"],
                "parameters": entry["parameters"],
                "strict": entry.get("strict", True),
            }
            for name, entry in self._entries.items()
            if allowed_effects is None
            or self.effect(name, {}).value in {item.value for item in allowed_effects}
        ]

    def definitions_for_mode(self, mode: CollaborationMode) -> list[dict[str, Any]]:
        """Expose only structurally valid tools for the active workflow mode."""
        if mode is CollaborationMode.IMPLEMENTATION:
            return self.definitions()
        allowed_names = (
            {
                "read",
                "search",
                "web_search",
                "web_fetch",
                "skill",
                "task",
                "request_user_input",
                "propose_plan",
            }
            if mode is CollaborationMode.PLAN
            else {"read", "search", "web_search", "web_fetch", "skill", "task"}
        )
        definitions = [
            definition
            for definition in self.definitions()
            if definition["name"] in allowed_names
        ]
        for definition in definitions:
            if definition["name"] == "task":
                definition["parameters"] = {
                    **definition["parameters"],
                    "properties": {
                        **definition["parameters"]["properties"],
                        "action": {
                            "type": "string",
                            "enum": ["list", "poll", "wait"],
                        },
                    },
                }
                definition["description"] = (
                    "Read existing execution-session state. list and poll return "
                    "immediately; wait observes completion for at most 30 seconds. "
                    "This workflow mode cannot start, write, check, interrupt, or "
                    "stop sessions."
                )
        return definitions

    def effect(self, name: str, arguments: dict[str, Any]) -> ToolEffect:
        """Classify unknown and dynamic tools conservatively as external."""
        entry = self._entries.get(name)
        if entry is None:
            return ToolEffect.EXTERNAL
        declared = entry.get("effect", ToolEffect.EXTERNAL)
        if callable(declared):
            declared = declared(arguments)
        try:
            return ToolEffect(declared)
        except (TypeError, ValueError):
            return ToolEffect.EXTERNAL

    def authorize(
        self,
        name: str,
        arguments: dict[str, Any],
        broker: PermissionBroker,
        *,
        cancellation_token: CancellationToken | None = None,
        event_sink=None,
    ):
        """Apply the permission boundary without dispatching the tool."""
        effect = self.effect(name, arguments)
        entry = self._entries.get(name)
        sandbox_check = None if entry is None else entry.get("sandbox_check")
        hard_check = None if entry is None else entry.get("hard_check")
        return broker.authorize(
            name,
            effect,
            arguments,
            hard_check=(lambda: hard_check(arguments)) if hard_check else None,
            sandbox_check=(lambda: sandbox_check(arguments)) if sandbox_check else None,
            cancellation_token=cancellation_token,
            event_sink=event_sink,
        )

    def parallel_safe(self, name: str) -> bool:
        """Return true only for tools explicitly safe to overlap."""
        entry = self._entries.get(name)
        return bool(entry is not None and entry.get("parallel_safe", False))

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
    agent_manager: AgentManager | None = None,
    sandbox_runtime: SandboxRuntime | None = None,
    web_runtime: WebRuntime | None = None,
) -> ToolRegistry:
    """Bind process-local task state to one immutable per-turn registry."""
    if (
        task_manager is None
        and todo_state is None
        and agent_manager is None
        and sandbox_runtime is None
        and web_runtime is None
    ):
        return DEFAULT_TOOL_REGISTRY
    entries = {name: dict(entry) for name, entry in TOOLS.items()}
    if sandbox_runtime is not None and sandbox_runtime.restricted:
        entries["execute"]["description"] = (
            "Run a POSIX shell command inside the active Linux sandbox. Short "
            "commands return normally; continuing commands keep the same named "
            "container and return a task ID. interactive=true allocates a real "
            "terminal. Use project-relative paths; the session cannot change its "
            "sandbox policy."
        )
    for name, function in {
        "read": read,
        "write": write,
        "search": search,
        "patch": patch,
        "delete": delete,
    }.items():
        entries[name]["function"] = lambda function=function, **arguments: function(
            **arguments,
            sandbox_runtime=sandbox_runtime,
        )
        write_effect = name in {"write", "patch", "delete"}
        entries[name]["sandbox_check"] = lambda arguments, write=write_effect: (
            sandbox_runtime.resolve_path(arguments["path"], write=write)
            if sandbox_runtime is not None
            else None
        )
        if write_effect:
            entries[name]["hard_check"] = lambda arguments: _protect_metadata_path(
                arguments["path"], sandbox_runtime
            )
    if todo_state is not None:
        entries["todo"]["function"] = lambda todos: _todo_for_state(todo_state, todos)
    if task_manager is not None:
        entries["execute"]["function"] = (
            lambda command, background=False, interactive=False, yield_time_ms=10_000, reason=None: (
                execute(
                    command,
                    background,
                    interactive,
                    yield_time_ms,
                    reason,
                    task_manager=task_manager,
                    cancellation_token=cancellation_token,
                    sandbox_runtime=sandbox_runtime,
                )
            )
        )
        entries["task"]["function"] = (
            lambda action, task_id=None, input=None, submit=True, command=None, timeout_seconds=10, reason=None: (
                task(
                    action,
                    task_id,
                    timeout_seconds,
                    input,
                    submit,
                    command,
                    reason,
                    task_manager=task_manager,
                    cancellation_token=cancellation_token,
                )
            )
        )
    if agent_manager is not None:
        entries["spawn_agent"]["function"] = (
            lambda description, prompt, isolation="worktree", fork_turns=0: spawn_agent(
                description,
                prompt,
                isolation,
                fork_turns,
                agent_manager=agent_manager,
            )
        )
        entries["agent"]["function"] = (
            lambda action, agent_id, message, timeout_seconds, confirm_discard=False: agent(
                action,
                agent_id,
                message,
                timeout_seconds,
                confirm_discard,
                agent_manager=agent_manager,
                cancellation_token=cancellation_token,
            )
        )
    if web_runtime is not None:
        entries["web_search"]["function"] = lambda query, count=5: web_search(
            query,
            count,
            web_runtime=web_runtime,
            cancellation_token=cancellation_token,
        )
        entries["web_fetch"]["function"] = lambda url: web_fetch(
            url,
            web_runtime=web_runtime,
            cancellation_token=cancellation_token,
        )
        for name in ("web_search", "web_fetch"):
            entries[name]["sandbox_check"] = lambda _arguments: (
                _require_web_network(sandbox_runtime)
            )
    return ToolRegistry(entries)


def build_child_tool_registry(
    todo_state: TodoState,
    cancellation_token: CancellationToken,
    task_manager: BackgroundTaskManager,
    sandbox_runtime: SandboxRuntime | None = None,
    web_runtime: WebRuntime | None = None,
) -> ToolRegistry:
    """Build a child-only registry with Agent-scoped execution sessions."""
    excluded = {"spawn_agent", "agent"}
    entries = {
        name: dict(entry) for name, entry in TOOLS.items() if name not in excluded
    }
    for name, function in {
        "read": read,
        "write": write,
        "search": search,
        "patch": patch,
        "delete": delete,
    }.items():
        entries[name]["function"] = lambda function=function, **arguments: function(
            **arguments,
            sandbox_runtime=sandbox_runtime,
        )
        write_effect = name in {"write", "patch", "delete"}
        entries[name]["sandbox_check"] = lambda arguments, write=write_effect: (
            sandbox_runtime.resolve_path(arguments["path"], write=write)
            if sandbox_runtime is not None
            else None
        )
        if write_effect:
            entries[name]["hard_check"] = lambda arguments: _protect_metadata_path(
                arguments["path"], sandbox_runtime
            )
    entries["execute"]["description"] = (
        "Run a POSIX command in the Agent's continuing sandbox session."
        if sandbox_runtime is not None and sandbox_runtime.restricted
        else "Run a command in the Agent's continuing host execution session."
    )
    entries["execute"]["function"] = (
        lambda command, background=False, interactive=False, yield_time_ms=10_000, reason=None: (
            execute(
                command,
                background,
                interactive,
                yield_time_ms,
                reason,
                task_manager=task_manager,
                cancellation_token=cancellation_token,
                sandbox_runtime=sandbox_runtime,
            )
        )
    )
    entries["task"]["function"] = (
        lambda action, task_id=None, input=None, submit=True, command=None, timeout_seconds=10, reason=None: (
            task(
                action,
                task_id,
                timeout_seconds,
                input,
                submit,
                command,
                reason,
                task_manager=task_manager,
                cancellation_token=cancellation_token,
            )
        )
    )
    entries["todo"]["function"] = lambda todos: _todo_for_state(todo_state, todos)
    if web_runtime is not None:
        entries["web_search"]["function"] = lambda query, count=5: web_search(
            query,
            count,
            web_runtime=web_runtime,
            cancellation_token=cancellation_token,
        )
        entries["web_fetch"]["function"] = lambda url: web_fetch(
            url,
            web_runtime=web_runtime,
            cancellation_token=cancellation_token,
        )
        for name in ("web_search", "web_fetch"):
            entries[name]["sandbox_check"] = lambda _arguments: (
                _require_web_network(sandbox_runtime)
            )
    else:
        entries.pop("web_search")
        entries.pop("web_fetch")
    return ToolRegistry(entries)


def _protect_metadata_path(path: str, sandbox_runtime: SandboxRuntime | None) -> None:
    """Keep application and Git metadata outside model-controlled file tools."""
    candidate = Path(path)
    if sandbox_runtime is not None:
        if not candidate.is_absolute():
            candidate = sandbox_runtime.config.cwd / candidate
        root = sandbox_runtime.config.project_root
    else:
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        root = Path.cwd()
    if any(part.casefold() in {".git", ".coding-kid"} for part in candidate.parts):
        raise PermissionError("protected project or application metadata")
    try:
        relative = candidate.resolve(strict=False).relative_to(root.resolve())
    except ValueError:
        return
    if relative.parts and relative.parts[0].casefold() in {".git", ".coding-kid"}:
        raise PermissionError(f"protected project metadata: {relative.parts[0]}")


def _protect_command(command: str) -> None:
    """Reject shell requests that explicitly target protected application metadata."""
    normalized = " ".join(command.casefold().split())
    protected = re.compile(r"(?:^|[\\/\s'\"])\.(?:git|coding-kid)(?:$|[\\/\s'\"])")
    if protected.search(normalized):
        raise PermissionError("command explicitly targets protected project metadata")


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
