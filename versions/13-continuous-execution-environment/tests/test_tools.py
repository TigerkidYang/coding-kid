from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

from coding_kid.background_tasks import BackgroundTaskManager
from coding_kid.tools import (
    MAX_TODO_CONTENT_CHARS,
    MAX_TODO_ITEMS,
    MAX_TOOL_OUTPUT_CHARS,
    TOOLS,
    TodoState,
    ToolRegistry,
    build_tool_registry,
    build_child_tool_registry,
    dispatch_tool,
    get_todos,
)
from coding_kid.terminal import CommandResult
from coding_kid.events import CancellationToken
from coding_kid.sandbox import SandboxConfig, SandboxMode, SandboxRuntime


def test_write_and_read_file(tmp_path: Path) -> None:
    path = tmp_path / "notes" / "lesson.txt"

    write_result = dispatch_tool(
        "write", {"path": str(path), "content": "first lesson"}
    )
    read_result = dispatch_tool("read", {"path": str(path)})

    assert write_result == f"Wrote {path}"
    assert read_result == "first lesson"


def test_patch_replaces_one_exact_text_fragment(tmp_path: Path) -> None:
    path = tmp_path / "example.py"
    path.write_text("answer = 41\n", encoding="utf-8")

    result = dispatch_tool(
        "patch",
        {"path": str(path), "old_text": "41", "new_text": "42"},
    )

    assert result == f"Patched {path}"
    assert path.read_text(encoding="utf-8") == "answer = 42\n"


def test_patch_rejects_missing_or_ambiguous_text(tmp_path: Path) -> None:
    path = tmp_path / "example.txt"
    path.write_text("same same", encoding="utf-8")

    missing = dispatch_tool(
        "patch",
        {"path": str(path), "old_text": "absent", "new_text": "new"},
    )
    ambiguous = dispatch_tool(
        "patch",
        {"path": str(path), "old_text": "same", "new_text": "new"},
    )

    assert missing.startswith("ERROR:")
    assert "not found" in missing
    assert ambiguous.startswith("ERROR:")
    assert "2 times" in ambiguous


def test_search_finds_file_names_and_text(tmp_path: Path) -> None:
    (tmp_path / "needle_name.py").write_text("nothing here\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("a needle in text\n", encoding="utf-8")

    result = dispatch_tool("search", {"query": "needle", "path": str(tmp_path)})

    assert "FILE needle_name.py" in result
    assert "TEXT other.py:1:a needle in text" in result


def test_search_treats_an_empty_path_as_the_current_directory(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "module.py").write_text("needle\n", encoding="utf-8")

    result = dispatch_tool("search", {"query": "needle", "path": ""})

    assert "TEXT module.py:1:needle" in result


def test_search_rejects_an_empty_query() -> None:
    result = dispatch_tool("search", {"query": "", "path": "."})

    assert result == "ERROR: ValueError: search query must not be empty"


def test_search_truncates_large_results(tmp_path: Path) -> None:
    path = tmp_path / "many.txt"
    path.write_text(
        "\n".join(f"match {number}" for number in range(150)), encoding="utf-8"
    )

    result = dispatch_tool("search", {"query": "match", "path": str(tmp_path)})

    assert len(result.splitlines()) == 101
    assert result.endswith("... search results truncated at 100 matches")


def test_search_rejects_a_missing_path(tmp_path: Path) -> None:
    result = dispatch_tool(
        "search", {"query": "needle", "path": str(tmp_path / "missing")}
    )

    assert result.startswith("ERROR: FileNotFoundError:")


def test_search_skips_generated_and_environment_directories(tmp_path: Path) -> None:
    (tmp_path / "source.py").write_text("needle\n", encoding="utf-8")
    hidden = tmp_path / ".venv"
    hidden.mkdir()
    (hidden / "dependency.py").write_text("needle\n", encoding="utf-8")

    result = dispatch_tool("search", {"query": "needle", "path": str(tmp_path)})

    assert "source.py" in result
    assert "dependency.py" not in result


def test_dispatch_bounds_large_tool_results(tmp_path: Path) -> None:
    path = tmp_path / "large.txt"
    path.write_text("x" * (MAX_TOOL_OUTPUT_CHARS + 1_000), encoding="utf-8")

    result = dispatch_tool("read", {"path": str(path)})

    assert "tool output truncated" in result
    assert len(result) < MAX_TOOL_OUTPUT_CHARS + 200


def test_delete_removes_file(tmp_path: Path) -> None:
    path = tmp_path / "temporary.txt"
    path.write_text("temporary", encoding="utf-8")

    result = dispatch_tool("delete", {"path": str(path)})

    assert result == f"Deleted {path}"
    assert not path.exists()


def test_restricted_registry_confines_file_tools(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    sandbox = SandboxRuntime(
        SandboxConfig(SandboxMode.WORKSPACE_WRITE, project, project),
        docker_executable="docker",
    )
    registry = build_tool_registry(sandbox_runtime=sandbox)

    allowed = registry.dispatch("write", {"path": "inside.txt", "content": "ok"})
    denied_read = registry.dispatch("read", {"path": "../outside.txt"})
    denied_metadata = registry.dispatch(
        "write", {"path": ".git/config", "content": "bad"}
    )

    assert "inside.txt" in allowed
    assert (project / "inside.txt").read_text(encoding="utf-8") == "ok"
    assert "outside project" in denied_read
    assert "protects workspace metadata" in denied_metadata
    assert outside.read_text(encoding="utf-8") == "secret"


def test_read_only_registry_rejects_mutation(tmp_path: Path) -> None:
    sandbox = SandboxRuntime(
        SandboxConfig(SandboxMode.READ_ONLY, tmp_path, tmp_path),
        docker_executable="docker",
    )
    registry = build_tool_registry(sandbox_runtime=sandbox)

    result = registry.dispatch("write", {"path": "blocked.txt", "content": "x"})

    assert "sandbox is read-only" in result
    assert not (tmp_path / "blocked.txt").exists()


def test_execute_returns_exit_code_stdout_and_stderr() -> None:
    command = (
        "python -c \"import sys; print('hello'); "
        "print('problem', file=sys.stderr); sys.exit(3)\""
    )

    result = dispatch_tool("execute", {"command": command})

    assert "exit_code: 3" in result
    assert "stdout:\nhello" in result
    assert "stderr:\nproblem" in result


def test_execute_timeout_returns_partial_model_readable_output(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        "coding_kid.tools.run_command",
        lambda command, **kwargs: CommandResult(124, "partial", "", True, 120.0),
    )

    result = dispatch_tool("execute", {"command": "slow command"})

    assert "exit_code: 124" in result
    assert "timed_out: true" in result
    assert "stdout:\npartial" in result


def test_unknown_tool_and_bad_arguments_become_errors() -> None:
    assert dispatch_tool("missing", {}).startswith("ERROR: Unknown tool")
    assert dispatch_tool("read", {}).startswith("ERROR:")


def test_every_tool_has_model_visible_metadata() -> None:
    assert set(TOOLS) == {
        "execute",
        "read",
        "write",
        "search",
        "patch",
        "delete",
        "todo",
        "task",
        "spawn_agent",
        "agent",
    }
    for name, tool in TOOLS.items():
        assert tool["description"]
        assert tool["parameters"]["type"] == "object"
        assert callable(tool["function"]), name
    assert TOOLS["search"]["parameters"]["properties"]["query"]["minLength"] == 1
    assert "literal" in TOOLS["search"]["description"]
    assert "not a glob" in TOOLS["search"]["description"]
    assert TOOLS["execute"]["parameters"]["properties"]["command"]["minLength"] == 1
    assert (
        TOOLS["execute"]["parameters"]["properties"]["background"]["default"] is False
    )
    for name in {"read", "write", "search", "patch", "delete"}:
        assert TOOLS[name]["parameters"]["properties"]["path"]["minLength"] == 1
    assert TOOLS["todo"]["parameters"]["required"] == ["todos"]
    todo_items = TOOLS["todo"]["parameters"]["properties"]["todos"]
    assert todo_items["maxItems"] == MAX_TODO_ITEMS
    assert (
        todo_items["items"]["properties"]["content"]["maxLength"]
        == MAX_TODO_CONTENT_CHARS
    )


def test_every_strict_tool_requires_each_declared_property() -> None:
    for definition in ToolRegistry().definitions():
        if not definition["strict"]:
            continue
        parameters = definition["parameters"]
        assert set(parameters["required"]) == set(parameters["properties"]), definition[
            "name"
        ]


def test_only_builtin_read_and_search_are_parallel_safe() -> None:
    registry = ToolRegistry()

    assert registry.parallel_safe("read")
    assert registry.parallel_safe("search")
    assert not registry.parallel_safe("write")
    assert not registry.parallel_safe("execute")
    assert not registry.parallel_safe("missing")


def test_background_execute_and_task_actions(tmp_path: Path) -> None:
    script = tmp_path / "worker.py"
    script.write_text("print('background result')\n", encoding="utf-8")
    manager = BackgroundTaskManager(id_factory=lambda: "task_bound")
    registry = build_tool_registry(manager)
    try:
        launched = registry.dispatch(
            "execute",
            {
                "command": f'& "{sys.executable}" "{script}"',
                "background": True,
            },
        )
        waited = registry.dispatch(
            "task",
            {"action": "wait", "task_id": "task_bound", "timeout_seconds": 10},
        )
        listed = registry.dispatch("task", {"action": "list"})
        stopped = registry.dispatch("task", {"action": "stop", "task_id": "task_bound"})
    finally:
        manager.close()

    assert "task_id: task_bound" in launched
    assert "status: completed" in waited
    assert "background result" in waited
    assert "task_bound  completed" in listed
    assert "status: completed" in stopped


def test_background_tools_require_a_bound_runtime() -> None:
    assert dispatch_tool(
        "execute", {"command": "Write-Output hi", "background": True}
    ).startswith("ERROR: RuntimeError:")
    assert dispatch_tool("task", {"action": "list"}).startswith("ERROR: RuntimeError:")


def test_todo_replaces_the_full_checklist() -> None:
    first = dispatch_tool(
        "todo",
        {
            "todos": [
                {"content": "Inspect bug", "status": "in_progress"},
                {"content": "Write fix", "status": "pending"},
            ]
        },
    )
    assert "1. [in_progress] Inspect bug" in first
    assert "2. [pending] Write fix" in first
    assert get_todos() == [
        {"content": "Inspect bug", "status": "in_progress"},
        {"content": "Write fix", "status": "pending"},
    ]

    second = dispatch_tool(
        "todo",
        {
            "todos": [
                {"content": "Inspect bug", "status": "completed"},
                {"content": "Write fix", "status": "in_progress"},
            ]
        },
    )
    assert "1. [completed] Inspect bug" in second
    assert get_todos()[1]["status"] == "in_progress"


def test_explicit_todo_states_are_isolated() -> None:
    root = TodoState([{"content": "Root", "status": "pending"}])
    child = TodoState()
    root_registry = build_tool_registry(todo_state=root)
    child_registry = build_tool_registry(todo_state=child)
    assert "todo" in root_registry.names

    child_registry.dispatch(
        "todo",
        {"todos": [{"content": "Child", "status": "in_progress"}]},
    )

    assert root.items == [{"content": "Root", "status": "pending"}]
    assert child.items == [{"content": "Child", "status": "in_progress"}]
    assert get_todos() == []


def test_agent_tools_bind_one_manager_and_use_strict_schemas() -> None:
    calls: list[tuple[Any, ...]] = []

    class FakeAgents:
        def start(self, description: str, prompt: str) -> Any:
            calls.append(("start", description, prompt))
            return SimpleNamespace(model_text=lambda: "agent_id: agent_1")

        def status_text(self) -> str:
            calls.append(("list",))
            return "agent_1 running"

        def poll(self, agent_id: str) -> Any:
            calls.append(("poll", agent_id))
            return SimpleNamespace(model_text=lambda: "status: completed")

        def wait(self, agent_id: str, timeout: float, token: Any) -> Any:
            calls.append(("wait", agent_id, timeout, token))
            snapshot = SimpleNamespace(
                model_text=lambda wait_timed_out=False: (
                    f"wait_timed_out: {str(wait_timed_out).lower()}"
                )
            )
            return snapshot, True

        def followup(self, agent_id: str, message: str) -> Any:
            calls.append(("followup", agent_id, message))
            return SimpleNamespace(model_text=lambda: "status: starting")

        def stop(self, agent_id: str, timeout: float) -> Any:
            calls.append(("stop", agent_id, timeout))
            return SimpleNamespace(model_text=lambda: "status: stopped")

    token = CancellationToken()
    registry = build_tool_registry(
        todo_state=TodoState(),
        cancellation_token=token,
        agent_manager=FakeAgents(),
    )

    assert (
        registry.dispatch(
            "spawn_agent", {"description": "inspect", "prompt": "read it"}
        )
        == "agent_id: agent_1"
    )
    assert (
        registry.dispatch(
            "agent",
            {
                "action": "wait",
                "agent_id": "agent_1",
                "message": None,
                "timeout_seconds": 3,
            },
        )
        == "wait_timed_out: true"
    )
    definitions = {item["name"]: item for item in registry.definitions()}
    assert definitions["spawn_agent"]["strict"] is True
    assert definitions["agent"]["parameters"]["required"] == [
        "action",
        "agent_id",
        "message",
        "timeout_seconds",
    ]
    assert calls == [
        ("start", "inspect", "read it"),
        ("wait", "agent_1", 3, token),
    ]


def test_child_registry_excludes_agents_but_scopes_execution_sessions() -> None:
    tasks = BackgroundTaskManager()
    registry = build_child_tool_registry(TodoState(), CancellationToken(), tasks)

    assert "spawn_agent" not in registry.names
    assert "agent" not in registry.names
    assert "task" in registry.names
    execute = next(item for item in registry.definitions() if item["name"] == "execute")
    assert "background" in execute["parameters"]["properties"]
    assert "interactive" in execute["parameters"]["properties"]
    tasks.close()


def test_todo_can_clear_a_finished_checklist() -> None:
    dispatch_tool(
        "todo",
        {"todos": [{"content": "Finished", "status": "completed"}]},
    )

    result = dispatch_tool("todo", {"todos": []})

    assert result == "Cleared todos."
    assert get_todos() == []


def test_todo_rejects_invalid_updates() -> None:
    two_active = dispatch_tool(
        "todo",
        {
            "todos": [
                {"content": "One", "status": "in_progress"},
                {"content": "Two", "status": "in_progress"},
            ]
        },
    )
    assert two_active.startswith("ERROR:")
    assert "at most one" in two_active
    assert get_todos() == []

    bad_status = dispatch_tool(
        "todo",
        {"todos": [{"content": "One", "status": "done"}]},
    )
    assert bad_status.startswith("ERROR:")
    assert "status" in bad_status


def test_todo_rejects_oversized_updates_without_changing_state() -> None:
    dispatch_tool(
        "todo",
        {"todos": [{"content": "Keep me", "status": "pending"}]},
    )

    too_many = dispatch_tool(
        "todo",
        {
            "todos": [
                {"content": f"Item {index}", "status": "pending"}
                for index in range(MAX_TODO_ITEMS + 1)
            ]
        },
    )
    too_long = dispatch_tool(
        "todo",
        {
            "todos": [
                {
                    "content": "x" * (MAX_TODO_CONTENT_CHARS + 1),
                    "status": "pending",
                }
            ]
        },
    )

    assert too_many.startswith("ERROR:")
    assert f"at most {MAX_TODO_ITEMS}" in too_many
    assert too_long.startswith("ERROR:")
    assert f"at most {MAX_TODO_CONTENT_CHARS}" in too_long
    assert get_todos() == [{"content": "Keep me", "status": "pending"}]
