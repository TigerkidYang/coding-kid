from typing import Any
from pathlib import Path
import sys
import threading
import time

import pytest

import coding_kid.cli as cli
from coding_kid.agents import AgentManager
from coding_kid.background_tasks import BackgroundTaskManager
from coding_kid.context import SessionContext
from coding_kid.context_manager import ContextBudget, ContextManager
from coding_kid.events import CancellationToken, EventSink
from coding_kid.memory import MemoryManager
from coding_kid.sessions import SessionStore


def test_chat_accepts_input_shows_tool_activity_and_exits(monkeypatch: Any) -> None:
    inputs = iter(["Create a file", "/exit"])
    outputs: list[str] = []
    received_messages: list[list[Any]] = []

    def fake_input(prompt: str) -> str:
        outputs.append(prompt)
        return next(inputs)

    def fake_run_turn(
        manager: Any,
        on_tool: Any,
        on_context: Any,
        session_context: Any,
    ) -> str:
        received_messages.append(manager.conversation.active_items())
        on_tool("write", {"path": "hello.txt", "content": "hello"}, "Wrote hello.txt")
        return "Created hello.txt."

    monkeypatch.setattr(cli, "run_turn", fake_run_turn)

    cli.chat(input_function=fake_input, output_function=outputs.append)

    assert received_messages == [[{"role": "user", "content": "Create a file"}]]
    rendered = "\n".join(outputs)
    assert "Coding Kid" in rendered
    assert "[tool] write: hello.txt" in rendered
    assert '"content": "hello"' not in rendered
    assert "Wrote hello.txt" not in rendered
    assert "Created hello.txt." in rendered


def test_chat_lists_stops_and_notifies_about_background_tasks(tmp_path: Path) -> None:
    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    tasks = BackgroundTaskManager()
    task_id = tasks.start(f'& "{sys.executable}" "{script}"').task_id
    inputs = iter(["/tasks", f"/task stop {task_id}", "/exit"])
    outputs: list[str] = []
    try:
        cli.chat(
            input_function=lambda prompt: next(inputs),
            output_function=outputs.append,
            background_tasks=tasks,
        )
    finally:
        tasks.close()

    rendered = "\n".join(outputs)
    assert task_id in rendered
    assert "running" in rendered
    assert f"Stopped {task_id} (stopped" in rendered


def test_chat_reports_completed_task_at_prompt_boundary(tmp_path: Path) -> None:
    script = tmp_path / "quick.py"
    script.write_text("print('done', flush=True)\n", encoding="utf-8")
    tasks = BackgroundTaskManager()
    task_id = tasks.start(f'& "{sys.executable}" "{script}"').task_id
    tasks.wait(task_id, 10)
    outputs: list[str] = []
    try:
        cli.chat(
            input_function=lambda prompt: "/exit",
            output_function=outputs.append,
            background_tasks=tasks,
        )
    finally:
        tasks.close()

    assert any(f"[task] {task_id} completed" in line for line in outputs)


def test_chat_controls_interactive_session_and_runs_readiness_check() -> None:
    tasks = BackgroundTaskManager(id_factory=lambda: "task_cli_terminal")
    task_id = tasks.start(f'& "{sys.executable}" -i -u', interactive=True).task_id
    deadline = time.monotonic() + 8
    while ">>>" not in tasks.poll(task_id).stdout and time.monotonic() < deadline:
        time.sleep(0.05)
    inputs = iter(
        [
            f"/task input {task_id} print('cli-input-ok')",
            f"/task poll {task_id}",
            f'/task check {task_id} & "{sys.executable}" -c "print(\'cli-ready\')"',
            f"/task interrupt {task_id}",
            f"/task stop {task_id}",
            "/exit",
        ]
    )
    outputs: list[str] = []
    try:
        cli.chat(
            input_function=lambda prompt: next(inputs),
            output_function=outputs.append,
            background_tasks=tasks,
        )
    finally:
        tasks.close()

    rendered = "\n".join(outputs)
    assert "cli-input-ok" in rendered
    assert "Readiness check evidence" in rendered
    assert "cli-ready" in rendered
    assert "interactive: true" in rendered


def test_chat_lists_stops_and_notifies_about_child_agents(tmp_path: Path) -> None:
    entered = threading.Event()

    def runner(
        manager: Any,
        todos: Any,
        message: str,
        token: CancellationToken,
        event_sink: EventSink,
    ) -> str:
        entered.set()
        while not token.cancelled:
            time.sleep(0.005)
        token.raise_if_cancelled()
        return "unreachable"

    current_context = SessionContext.capture(tmp_path)
    agents = AgentManager(
        current_context, ContextBudget(None, "test"), child_runner=runner
    )
    agent_id = agents.start("slow child", "wait").agent_id
    assert entered.wait(1)
    inputs = iter(["/agents", f"/agent stop {agent_id}", "/exit"])
    outputs: list[str] = []
    try:
        cli.chat(
            input_function=lambda prompt: next(inputs),
            output_function=outputs.append,
            agent_manager=agents,
        )
    finally:
        agents.close()

    rendered = "\n".join(outputs)
    assert f"[agent] {agent_id} started" in rendered
    assert agent_id in rendered and "running" in rendered
    assert f"Agent {agent_id}: stopped." in rendered


def test_chat_reports_an_error_and_keeps_running(monkeypatch: Any) -> None:
    inputs = iter(["broken task", "/exit"])
    outputs: list[str] = []

    def fake_run_turn(
        manager: Any,
        on_tool: Any,
        on_context: Any,
        session_context: Any,
    ) -> str:
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(cli, "run_turn", fake_run_turn)

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=outputs.append,
    )

    assert any("model unavailable" in line for line in outputs)


def test_chat_handles_task_interruption_without_a_traceback(monkeypatch: Any) -> None:
    inputs = iter(["long task", "/exit"])
    outputs: list[str] = []

    def interrupted_run_turn(
        manager: Any,
        on_tool: Any,
        on_context: Any,
        session_context: Any,
    ) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_turn", interrupted_run_turn)

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=outputs.append,
    )

    assert any("Task interrupted" in line for line in outputs)
    assert outputs[-1] == "Goodbye."


def test_chat_retains_committed_failed_turn_evidence(monkeypatch: Any) -> None:
    inputs = iter(["first task", "second task", "/exit"])
    received_messages: list[list[Any]] = []

    def fake_run_turn(
        manager: Any,
        on_tool: Any,
        on_context: Any,
        session_context: Any,
    ) -> str:
        received_messages.append(manager.conversation.active_items())
        if len(received_messages) == 1:
            manager.conversation.append_model_round(
                [{"type": "partial-provider-output"}]
            )
            raise RuntimeError("failed")
        return "Second task completed."

    monkeypatch.setattr(cli, "run_turn", fake_run_turn)

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=lambda text: None,
    )

    assert received_messages[1] == [
        {"role": "user", "content": "first task"},
        {"type": "partial-provider-output"},
        {"role": "user", "content": "second task"},
    ]


def test_chat_preserves_successful_turns(monkeypatch: Any) -> None:
    inputs = iter(["first", "second", "/exit"])
    received_messages: list[list[Any]] = []

    def fake_run_turn(
        manager: Any,
        on_tool: Any,
        on_context: Any,
        session_context: Any,
    ) -> str:
        received_messages.append(manager.conversation.active_items())
        manager.conversation.append_model_round(
            [{"role": "assistant", "content": "done"}]
        )
        return "done"

    monkeypatch.setattr(cli, "run_turn", fake_run_turn)

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=lambda text: None,
    )

    assert received_messages[1] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "done"},
        {"role": "user", "content": "second"},
    ]


def test_chat_never_prints_a_blank_assistant_answer(monkeypatch: Any) -> None:
    inputs = iter(["answer me", "/exit"])
    outputs: list[str] = []

    monkeypatch.setattr(
        cli,
        "run_turn",
        lambda manager, on_tool, on_context, session_context: "   ",
    )

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=outputs.append,
    )

    assert "Coding Kid>    " not in outputs
    assert any("empty" in line.lower() for line in outputs)


def test_chat_hides_tool_results_but_shows_tool_errors(monkeypatch: Any) -> None:
    inputs = iter(["inspect files", "/exit"])
    outputs: list[str] = []

    def fake_run_turn(
        manager: Any,
        on_tool: Any,
        on_context: Any,
        session_context: Any,
    ) -> str:
        on_tool(
            "read",
            {"path": "secret.txt"},
            "the complete private file contents",
        )
        on_tool(
            "patch",
            {
                "path": "missing.txt",
                "old_text": "large old content",
                "new_text": "large new content",
            },
            "ERROR: FileNotFoundError: missing.txt",
        )
        return "Inspection finished."

    monkeypatch.setattr(cli, "run_turn", fake_run_turn)

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=outputs.append,
    )

    rendered = "\n".join(outputs)
    assert "[tool] read: secret.txt" in rendered
    assert "[tool] patch: missing.txt" in rendered
    assert "complete private file contents" not in rendered
    assert "large old content" not in rendered
    assert "large new content" not in rendered
    assert "ERROR: FileNotFoundError: missing.txt" in rendered


def test_format_tool_call_keeps_each_action_compact() -> None:
    cases = [
        ("execute", {"command": "pytest"}, "[tool] execute: pytest"),
        ("read", {"path": "app.py"}, "[tool] read: app.py"),
        (
            "search",
            {"query": "needle", "path": "src"},
            '[tool] search: "needle" in src',
        ),
        ("write", {"path": "new.py", "content": "hidden"}, "[tool] write: new.py"),
        (
            "patch",
            {"path": "app.py", "old_text": "hidden", "new_text": "hidden"},
            "[tool] patch: app.py",
        ),
        ("delete", {"path": "old.py"}, "[tool] delete: old.py"),
        (
            "todo",
            {
                "todos": [
                    {"content": "One", "status": "in_progress"},
                    {"content": "Two", "status": "completed"},
                ]
            },
            "[tool] todo: 2 items (1 in progress, 1 done)",
        ),
    ]

    for name, arguments, expected in cases:
        assert cli.format_tool_call(name, arguments) == expected


def test_chat_retains_todos_from_a_failed_turn(monkeypatch: Any) -> None:
    from coding_kid.tools import TodoState

    inputs = iter(["first task", "second task", "/exit"])
    received_messages: list[list[Any]] = []

    def fake_run_turn(
        manager: Any,
        on_tool: Any,
        on_context: Any,
        session_context: Any,
        todo_state: TodoState,
    ) -> str:
        received_messages.append(manager.conversation.active_items())
        if len(received_messages) == 1:
            todo_state.replace([{"content": "Keep me", "status": "pending"}])
            return "First task completed."
        if len(received_messages) == 2:
            todo_state.replace([{"content": "Temporary", "status": "in_progress"}])
            raise RuntimeError("failed")
        raise AssertionError("unexpected turn")

    monkeypatch.setattr(cli, "run_turn", fake_run_turn)

    state = TodoState()
    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=lambda text: None,
        todo_state=state,
    )

    assert state.items == [{"content": "Temporary", "status": "in_progress"}]
    assert received_messages[1] == [
        {"role": "user", "content": "first task"},
        {"role": "user", "content": "second task"},
    ]


def test_chat_starts_with_a_fresh_todo_session() -> None:
    from coding_kid.tools import TodoState

    state = TodoState()
    cli.chat(
        input_function=lambda prompt: "/exit",
        output_function=lambda text: None,
        todo_state=state,
    )

    assert state.items == []


def test_chat_reuses_one_session_context_for_all_turns(monkeypatch: Any) -> None:
    inputs = iter(["first", "second", "/exit"])
    contexts: list[Any] = []

    def fake_run_turn(
        manager: Any,
        on_tool: Any,
        on_context: Any,
        session_context: Any,
    ) -> str:
        contexts.append(session_context)
        return "done"

    monkeypatch.setattr(cli, "run_turn", fake_run_turn)

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=lambda text: None,
    )

    assert len(contexts) == 2
    assert contexts[0] is contexts[1]


def test_chat_reports_project_instruction_initialization_errors(
    monkeypatch: Any,
) -> None:
    outputs: list[str] = []

    def fail_capture() -> None:
        raise RuntimeError("Could not load project instructions from AGENTS.md")

    monkeypatch.setattr(cli.SessionContext, "capture", fail_capture)

    cli.chat(
        input_function=lambda prompt: "/exit",
        output_function=outputs.append,
    )

    assert outputs == ["Error: Could not load project instructions from AGENTS.md"]


def test_format_tool_call_bounds_and_flattens_model_arguments() -> None:
    rendered = cli.format_tool_call("execute", {"command": "x\n" + "y" * 500})

    assert "\n" not in rendered
    assert len(rendered) <= 140
    assert rendered.endswith("...")


def test_chat_recovers_when_the_display_codec_rejects_tool_text(
    monkeypatch: Any,
) -> None:
    inputs = iter(["verify unicode", "/exit"])
    outputs: list[str] = []

    def gbk_only_output(text: str) -> None:
        text.encode("gbk")
        outputs.append(text)

    def fake_run_turn(manager: Any, on_tool: Any, **kwargs: Any) -> str:
        on_tool("execute", {"command": "Write-Output ✳"}, "exit_code: 0")
        return "Verified."

    monkeypatch.setattr(cli, "run_turn", fake_run_turn)

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=gbk_only_output,
    )

    assert any(r"\u2733" in output for output in outputs)
    assert any("Verified." in output for output in outputs)


def test_format_search_call_displays_an_empty_path_as_current_directory() -> None:
    rendered = cli.format_tool_call("search", {"query": "def ", "path": ""})

    assert rendered == '[tool] search: "def " in .'


def test_main_uses_plain_chat_when_terminal_is_not_interactive(
    monkeypatch: Any,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(
        cli,
        "chat",
        lambda *, session_handle, memory_manager: calls.append("plain"),
    )

    cli.main(cli.SessionOptions(sandbox_mode="danger-full-access"))

    assert calls == ["plain"]


def test_main_uses_tui_when_terminal_is_interactive(monkeypatch: Any) -> None:
    import coding_kid.tui as tui

    calls: list[str] = []
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(
        tui,
        "run_tui",
        lambda context, manager, *, session_handle, memory_manager: calls.append("tui"),
    )

    cli.main(cli.SessionOptions(sandbox_mode="danger-full-access"))

    assert calls == ["tui"]


def test_context_command_reports_status_without_calling_model(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    context = SessionContext(
        cwd=tmp_path,
        operating_system="Windows 11",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-08-03",
        project_root=tmp_path,
        project_instructions=(),
    )
    manager = ContextManager(context, ContextBudget(None, "test passive"))
    monkeypatch.setattr(cli.SessionContext, "capture", lambda: context)
    monkeypatch.setattr(cli.ContextManager, "capture", lambda captured: manager)
    monkeypatch.setattr(
        cli,
        "run_turn",
        lambda *args, **kwargs: pytest.fail("model should not be called"),
    )
    outputs: list[str] = []
    inputs = iter(["/context", "/exit"])

    cli.chat(lambda prompt: next(inputs), outputs.append)

    assert any("Context mode: passive" in output for output in outputs)


def test_compact_command_uses_manual_trigger_and_keeps_chat_running(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    context = SessionContext(
        cwd=tmp_path,
        operating_system="Windows 11",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-08-03",
        project_root=tmp_path,
        project_instructions=(),
    )
    manager = ContextManager(context, ContextBudget(None, "test"))
    manager.conversation.append_user("old")
    manager.conversation.append_model_round([{"content": "work"}])
    manager.conversation.append_user("latest")
    triggers: list[str] = []
    monkeypatch.setattr(cli.SessionContext, "capture", lambda: context)
    monkeypatch.setattr(cli.ContextManager, "capture", lambda captured: manager)

    def fake_compact(*args: Any, trigger: str, on_context: Any, **kwargs: Any) -> bool:
        triggers.append(trigger)
        on_context("[context] compacting: manual")
        return True

    monkeypatch.setattr(cli, "compact_context", fake_compact)
    outputs: list[str] = []
    inputs = iter(["/compact", "/exit"])

    cli.chat(lambda prompt: next(inputs), outputs.append)

    assert triggers == ["manual"]
    assert "[context] compacting: manual" in outputs


def test_persistent_chat_commits_success_and_restores_it(
    monkeypatch: Any, tmp_path: Any
) -> None:
    context = SessionContext(
        cwd=tmp_path,
        operating_system="Windows 11",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-08-04",
        project_root=tmp_path,
        project_instructions=(),
    )
    manager = ContextManager(context, ContextBudget(32_768, "test"))
    store = SessionStore(tmp_path, home=tmp_path / "home")
    handle = store.create(context, manager, [])

    def fake_turn(manager: Any, **kwargs: Any) -> str:
        manager.conversation.append_model_round(
            [{"role": "assistant", "content": "persisted"}]
        )
        return "persisted"

    monkeypatch.setattr(cli, "run_turn", fake_turn)
    inputs = iter(["Remember this", "/exit"])
    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=lambda text: None,
        session_handle=handle,
    )
    session_id = handle.info.session_id
    handle.close()

    resumed = store.resume(session_id)
    assert resumed.manager.conversation.active_items() == [
        {"role": "user", "content": "Remember this"},
        {"role": "assistant", "content": "persisted"},
    ]


def test_persistent_chat_audits_failure_without_resuming_failed_state(
    monkeypatch: Any, tmp_path: Any
) -> None:
    context = SessionContext(
        cwd=tmp_path,
        operating_system="Windows 11",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-08-04",
        project_root=tmp_path,
        project_instructions=(),
    )
    manager = ContextManager(context, ContextBudget(32_768, "test"))
    store = SessionStore(tmp_path, home=tmp_path / "home")
    handle = store.create(context, manager, [])
    monkeypatch.setattr(
        cli,
        "run_turn",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("failed")),
    )
    inputs = iter(["Do not retain", "/exit"])

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=lambda text: None,
        session_handle=handle,
    )
    session_id = handle.info.session_id
    handle.close()

    resumed = store.resume(session_id)
    assert resumed.manager.conversation.transcript == []


def test_plain_chat_exposes_manual_memory_commands(
    monkeypatch: Any, tmp_path: Any
) -> None:
    monkeypatch.setenv("CODING_KID_MEMORY_MODE", "manual")
    context = SessionContext(
        cwd=tmp_path,
        operating_system="Windows 11",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-08-04",
        project_root=tmp_path,
        project_instructions=(),
    )
    manager = ContextManager(context, ContextBudget(32_768, "test"))
    store = SessionStore(tmp_path, home=tmp_path / "home")
    handle = store.create(context, manager, [])
    memories = MemoryManager(store)
    inputs = iter(
        [
            "/remember Use ALPHA naming",
            "/memory search ALPHA",
            "/memory",
            "/exit",
        ]
    )
    outputs: list[str] = []

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=outputs.append,
        session_handle=handle,
        memory_manager=memories,
    )

    rendered = "\n".join(outputs)
    assert "Remembered" in rendered
    assert "ALPHA naming" in rendered
    assert "mode=manual" in rendered


def test_resume_rejects_a_different_model(tmp_path: Any) -> None:
    original = SessionContext(
        cwd=tmp_path,
        operating_system="Windows 11",
        shell="cmd.exe",
        model="original/model",
        local_date="2026-08-04",
        project_root=tmp_path,
        project_instructions=(),
    )
    store = SessionStore(tmp_path, home=tmp_path / "home")
    handle = store.create(
        original,
        ContextManager(original, ContextBudget(32_768, "test")),
        [],
    )
    session_id = handle.info.session_id
    handle.close()
    current = SessionContext(
        cwd=tmp_path,
        operating_system="Windows 11",
        shell="cmd.exe",
        model="different/model",
        local_date="2026-08-04",
        project_root=tmp_path,
        project_instructions=(),
    )

    with pytest.raises(cli.SessionError, match="original/model"):
        cli._open_session(
            cli.SessionOptions(mode="resume", session_id=session_id),
            current,
            store,
        )
