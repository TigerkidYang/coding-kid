from __future__ import annotations

import asyncio
import json
import sys
import time
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from textual.widgets import Static

from coding_kid.agents import AgentManager
from coding_kid.context import SessionContext
from coding_kid.background_tasks import BackgroundTaskManager
from coding_kid.context_manager import ContextBudget, ContextManager
from coding_kid.events import CancellationToken, EventSink, ToolCompleted
from coding_kid.memory import MemoryManager
from coding_kid.checkpoints import CheckpointManager
from coding_kid.permissions import PermissionBroker
from coding_kid.sessions import SessionStore
from coding_kid.sandbox import SandboxConfig, SandboxMode, SandboxRuntime
from coding_kid.tui import AssistantCell, CodingKidApp, Composer
from coding_kid.workflow import ApprovalPolicy, WorkflowState
from coding_kid.workflow_runtime import WorkflowRuntime


def text_message(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="message",
        content=[SimpleNamespace(type="output_text", text=text)],
    )


def tool_call(call_id: str, name: str, arguments: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        type="function_call",
        call_id=call_id,
        name=name,
        arguments=json.dumps(arguments),
    )


def response(*items: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(output=list(items), usage=None)


def make_app(
    tmp_path: Path,
    *,
    provider: Any | None = None,
    streaming_provider: Any | None = None,
    background_tasks: BackgroundTaskManager | None = None,
    agent_manager: AgentManager | None = None,
    sandbox_runtime: SandboxRuntime | None = None,
    permission_broker: PermissionBroker | None = None,
    workflow_runtime: WorkflowRuntime | None = None,
) -> CodingKidApp:
    context = SessionContext(
        cwd=tmp_path,
        operating_system="Windows 11",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-08-04",
        project_root=tmp_path,
        project_instructions=(),
    )
    manager = ContextManager(context, ContextBudget(100_000, "test"))
    return CodingKidApp(
        context,
        manager,
        provider=provider or (lambda *args, **kwargs: response(text_message("ok"))),
        streaming_provider=streaming_provider
        or (lambda *args, **kwargs: response(text_message("ok"))),
        background_tasks=background_tasks,
        agent_manager=agent_manager,
        sandbox_runtime=sandbox_runtime,
        permission_broker=permission_broker,
        workflow_runtime=workflow_runtime,
    )


def make_persistent_app(tmp_path: Path, streaming_provider: Any) -> CodingKidApp:
    context = SessionContext(
        cwd=tmp_path,
        operating_system="Windows 11",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-08-04",
        project_root=tmp_path,
        project_instructions=(),
    )
    manager = ContextManager(context, ContextBudget(100_000, "test"))
    store = SessionStore(tmp_path, home=tmp_path / "home")
    handle = store.create(context, manager, [])
    return CodingKidApp(
        context,
        manager,
        streaming_provider=streaming_provider,
        session_handle=handle,
    )


def content(widget: Static) -> str:
    return str(widget.content)


def test_tui_renders_codex_style_session_header_and_footer(tmp_path: Path) -> None:
    async def exercise() -> None:
        app = make_app(tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert "Coding Kid" in content(app.query_one(".session-card", Static))
            assert "test/model" in content(app.query_one("#footer-left", Static))
            assert "100% context left" in content(
                app.query_one("#footer-right", Static)
            )
            assert app.query_one(Composer).has_focus

    asyncio.run(exercise())


def test_tui_displays_sandbox_status_command(tmp_path: Path) -> None:
    async def exercise() -> None:
        sandbox = SandboxRuntime(
            SandboxConfig(SandboxMode.READ_ONLY, tmp_path, tmp_path),
            docker_executable="docker",
        )
        app = make_app(tmp_path, sandbox_runtime=sandbox)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            header = content(app.query_one(".session-card", Static))
            assert "v14" in header
            assert "read-only" in header
            composer = app.query_one(Composer)
            composer.load_text("/sandbox")
            composer.action_submit()
            await pilot.pause()
            transcript = "\n".join(
                content(item) for item in app.query(Static) if item.id is None
            )
            assert "Backend: docker" in transcript
            assert "Network: disabled" in transcript

    asyncio.run(exercise())


def test_tui_displays_three_permission_axes_and_switches_mode(tmp_path: Path) -> None:
    async def exercise() -> None:
        state = WorkflowState()
        broker = PermissionBroker(ApprovalPolicy.AUTO, state)
        sandbox = SandboxRuntime(
            SandboxConfig(SandboxMode.DANGER_FULL_ACCESS, tmp_path, tmp_path)
        )
        app = make_app(tmp_path, sandbox_runtime=sandbox, permission_broker=broker)
        async with app.run_test(size=(100, 28)) as pilot:
            await pilot.pause()
            composer = app.query_one(Composer)
            composer.load_text("/permissions")
            composer.action_submit()
            await pilot.pause()
            composer.load_text("/mode plan")
            composer.action_submit()
            await pilot.pause()
            transcript = "\n".join(
                content(item) for item in app.query(Static) if item.id is None
            )
            footer = content(app.query_one("#footer-left", Static))
            assert "Approval policy: auto" in transcript
            assert "Sandbox policy: danger-full-access" in transcript
            assert "Workflow mode: plan" in transcript
            assert "plan · auto · danger-full-access" in footer

    asyncio.run(exercise())


def test_tui_approval_denial_has_no_side_effect_and_accepts_feedback(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        target = tmp_path / "guarded.txt"
        target.write_text("before", encoding="utf-8")
        subprocess.run(["git", "-C", str(tmp_path), "add", "guarded.txt"], check=True)
        state = WorkflowState()
        broker = PermissionBroker(ApprovalPolicy.CAUTIOUS, state)
        sandbox = SandboxRuntime(
            SandboxConfig(SandboxMode.DANGER_FULL_ACCESS, tmp_path, tmp_path)
        )
        workflow = WorkflowRuntime(
            state, CheckpointManager(tmp_path, tmp_path / "app-state")
        )
        responses = iter(
            [
                response(
                    tool_call(
                        "call-1",
                        "write",
                        {"path": "guarded.txt", "content": "after"},
                    )
                ),
                response(text_message("Permission handled.")),
            ]
        )
        app = make_app(
            tmp_path,
            streaming_provider=lambda *args, **kwargs: next(responses),
            sandbox_runtime=sandbox,
            permission_broker=broker,
            workflow_runtime=workflow,
        )
        async with app.run_test(size=(100, 30)) as pilot:
            composer = app.query_one(Composer)
            composer.load_text("change guarded file")
            composer.action_submit()
            for _ in range(100):
                await pilot.pause(0.02)
                if broker.pending:
                    break
            assert broker.pending
            composer.load_text("3 keep the original")
            composer.action_submit()
            for _ in range(100):
                await pilot.pause(0.02)
                if not app.active_turn:
                    break
            assert not app.active_turn
            assert target.read_text(encoding="utf-8") == "before"
            transcript = "\n".join(
                content(item) for item in app.query(Static) if item.id is None
            )
            assert "Permission required" in transcript
            assert "keep the original" in transcript

    asyncio.run(exercise())


def test_tui_shows_background_events_tasks_and_running_count(tmp_path: Path) -> None:
    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    tasks = BackgroundTaskManager()
    task_id = tasks.start(f'& "{sys.executable}" "{script}"').task_id

    async def exercise() -> None:
        app = make_app(tmp_path, background_tasks=tasks)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.2)
            assert "1 terminal" in content(app.query_one("#footer-right", Static))
            notices = [content(widget) for widget in app.query(".notice-cell")]
            assert any(task_id in notice and "started" in notice for notice in notices)

            app.query_one(Composer).load_text("/tasks")
            await pilot.press("enter")
            await pilot.pause()
            contexts = [content(widget) for widget in app.query(".context-cell")]
            assert any(task_id in item and "running" in item for item in contexts)

            app.query_one(Composer).load_text(f"/task stop {task_id}")
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert tasks.poll(task_id).status == "stopped"
            assert "terminal" not in content(app.query_one("#footer-right", Static))

    try:
        asyncio.run(exercise())
    finally:
        tasks.close()


def test_tui_controls_interactive_terminal_and_readiness_check(tmp_path: Path) -> None:
    tasks = BackgroundTaskManager(id_factory=lambda: "task_tui_terminal")
    task_id = tasks.start(f'& "{sys.executable}" -i -u', interactive=True).task_id
    deadline = time.monotonic() + 8
    while ">>>" not in tasks.poll(task_id).stdout and time.monotonic() < deadline:
        time.sleep(0.05)

    async def exercise() -> None:
        app = make_app(tmp_path, background_tasks=tasks)
        async with app.run_test(size=(90, 28)) as pilot:
            await pilot.pause()
            composer = app.query_one(Composer)
            composer.load_text(f"/task input {task_id} print('tui-input-ok')")
            await pilot.press("enter")
            await pilot.pause(1.5)

            composer.load_text(
                f'/task check {task_id} & "{sys.executable}" -c "print(\'tui-ready\')"'
            )
            await pilot.press("enter")
            await pilot.pause(1.5)

            composer.load_text(f"/task interrupt {task_id}")
            await pilot.press("enter")
            await pilot.pause(1.5)
            assert tasks.poll(task_id).status == "running"

            contexts = "\n".join(
                content(widget) for widget in app.query(".context-cell")
            )
            assert "tui-input-ok" in contexts
            assert "Readiness check evidence" in contexts
            assert "tui-ready" in contexts

            composer.load_text(f"/task stop {task_id}")
            await pilot.press("enter")
            for _ in range(20):
                await pilot.pause(0.25)
                if tasks.poll(task_id).status == "stopped":
                    break
            assert tasks.poll(task_id).status == "stopped"

    try:
        asyncio.run(exercise())
    finally:
        tasks.close()


def test_tui_shows_agent_events_list_stop_and_running_count(tmp_path: Path) -> None:
    def runner(
        manager: Any,
        todos: Any,
        message: str,
        token: CancellationToken,
        event_sink: EventSink,
    ) -> str:
        while not token.cancelled:
            time.sleep(0.005)
        token.raise_if_cancelled()
        return "unreachable"

    current_context = SessionContext.capture(tmp_path)
    agents = AgentManager(
        current_context, ContextBudget(None, "test"), child_runner=runner
    )
    agent_id = agents.start("slow child", "wait").agent_id

    async def exercise() -> None:
        app = make_app(tmp_path, agent_manager=agents)
        async with app.run_test(size=(72, 20)) as pilot:
            await pilot.pause(0.2)
            assert "1 Agent" in content(app.query_one("#footer-right", Static))
            notices = [content(widget) for widget in app.query(".notice-cell")]
            assert any(agent_id in notice and "started" in notice for notice in notices)

            app.query_one(Composer).load_text("/agents")
            await pilot.press("enter")
            await pilot.pause()
            contexts = [content(widget) for widget in app.query(".context-cell")]
            assert any(agent_id in item and "running" in item for item in contexts)

            app.query_one(Composer).load_text(f"/agent stop {agent_id}")
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert agents.poll(agent_id).status == "stopped"
            assert "Agent" not in content(app.query_one("#footer-right", Static))

    try:
        asyncio.run(exercise())
    finally:
        agents.close()


def test_tui_submits_and_consolidates_streaming_answer_once(tmp_path: Path) -> None:
    def stream_provider(*args: Any, on_text_delta: Any, **kwargs: Any) -> Any:
        on_text_delta("Hello")
        on_text_delta(" **world**")
        return response(text_message("Hello **world**"))

    async def exercise() -> None:
        app = make_app(tmp_path, streaming_provider=stream_provider)
        async with app.run_test(size=(80, 24)) as pilot:
            composer = app.query_one(Composer)
            composer.load_text("Say hello")
            await pilot.press("enter")
            await pilot.pause(0.25)

            cells = list(app.query(AssistantCell))
            assert len(cells) == 1
            assert cells[0].source_text == "Hello **world**"
            assert not app.active_turn
            users = list(app.query(".user-cell"))
            assert len(users) == 1
            assert "Say hello" in content(users[0])

    asyncio.run(exercise())


def test_tui_mounts_terminal_only_answer_with_its_final_source(tmp_path: Path) -> None:
    def stream_provider(*args: Any, **kwargs: Any) -> Any:
        return response(text_message("TERMINAL_ONLY_ANSWER"))

    async def exercise() -> None:
        app = make_app(tmp_path, streaming_provider=stream_provider)
        async with app.run_test(size=(80, 24)) as pilot:
            app.query_one(Composer).load_text("Answer without a delta")
            await pilot.press("enter")
            await pilot.pause(0.25)

            cells = list(app.query(AssistantCell))
            assert len(cells) == 1
            assert cells[0].source_text == "TERMINAL_ONLY_ANSWER"
            assert "TERMINAL_ONLY_ANSWER" in str(cells[0].markdown._markdown)

    asyncio.run(exercise())


def test_tui_terminal_only_answer_renders_after_interrupt(tmp_path: Path) -> None:
    calls = 0

    def stream_provider(
        *args: Any,
        on_text_delta: Any,
        cancellation_token: Any,
        **kwargs: Any,
    ) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            on_text_delta("partial")
            while not cancellation_token.cancelled:
                time.sleep(0.005)
            cancellation_token.raise_if_cancelled()
        return response(text_message("RECOVERED_AFTER_INTERRUPT"))

    async def exercise() -> None:
        app = make_app(tmp_path, streaming_provider=stream_provider)
        async with app.run_test(size=(80, 24)) as pilot:
            composer = app.query_one(Composer)
            composer.load_text("Wait")
            await pilot.press("enter")
            await pilot.pause(0.1)
            await pilot.press("escape")
            await pilot.pause(0.2)
            composer.load_text("Recover")
            await pilot.press("enter")
            await pilot.pause(0.25)

            cells = list(app.query(AssistantCell))
            assert len(cells) == 1
            assert cells[0].source_text == "RECOVERED_AFTER_INTERRUPT"
            assert "RECOVERED_AFTER_INTERRUPT" in str(cells[0].markdown._markdown)

    asyncio.run(exercise())


def test_tui_commits_successful_turn_to_persistent_session(tmp_path: Path) -> None:
    def stream_provider(*args: Any, on_text_delta: Any, **kwargs: Any) -> Any:
        on_text_delta("Durable")
        return response(text_message("Durable"))

    async def exercise() -> None:
        app = make_persistent_app(tmp_path, stream_provider)
        async with app.run_test(size=(80, 24)) as pilot:
            app.query_one(Composer).load_text("Persist me")
            await pilot.press("enter")
            await pilot.pause(0.25)

            handle = app.session_handle
            assert handle is not None
            session_id = handle.info.session_id
            handle.close()
            resumed = handle.store.resume(session_id)
            assert (
                resumed.manager.conversation.active_items()[0]["content"]
                == "Persist me"
            )

    asyncio.run(exercise())


def test_tui_exposes_memory_add_search_and_status(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.setenv("CODING_KID_MEMORY_MODE", "manual")
    app = make_persistent_app(
        tmp_path,
        lambda *args, **kwargs: response(text_message("unused")),
    )
    assert app.session_handle is not None
    app.memory_manager = MemoryManager(app.session_handle.store)

    async def exercise() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            composer = app.query_one(Composer)
            for command in (
                "/remember Use ALPHA naming",
                "/memory search ALPHA",
                "/memory",
            ):
                composer.load_text(command)
                await pilot.press("enter")
                await pilot.pause()

            cells = [content(widget) for widget in app.query(".context-cell")]
            assert any("Remembered" in item for item in cells)
            assert any("ALPHA naming" in item for item in cells)
            assert any("mode=manual" in item for item in cells)

    asyncio.run(exercise())


def test_tui_renders_todo_as_codex_updated_plan(tmp_path: Path) -> None:
    responses = iter(
        [
            response(
                tool_call(
                    "todo-1",
                    "todo",
                    {
                        "todos": [
                            {"content": "Inspect", "status": "completed"},
                            {"content": "Finish", "status": "completed"},
                        ]
                    },
                )
            ),
            response(text_message("Done.")),
        ]
    )

    def stream_provider(*args: Any, on_text_delta: Any, **kwargs: Any) -> Any:
        current = next(responses)
        if current.output[0].type == "message":
            on_text_delta("Done.")
        return current

    async def exercise() -> None:
        app = make_app(tmp_path, streaming_provider=stream_provider)
        async with app.run_test(size=(80, 24)) as pilot:
            app.query_one(Composer).load_text("Do two things")
            await pilot.press("enter")
            await pilot.pause(0.25)

            plans = list(app.query(".todo-cell"))
            assert len(plans) == 1
            rendered = content(plans[0])
            assert "Updated Plan" in rendered
            assert "✔ Inspect" in rendered
            assert "✔ Finish" in rendered

    asyncio.run(exercise())


def test_tui_renders_existing_tool_families_and_errors(tmp_path: Path) -> None:
    async def exercise() -> None:
        app = make_app(tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            app.handle_turn_event(ToolCompleted("read", {"path": "a.py"}, "ok"))
            app.handle_turn_event(
                ToolCompleted("execute", {"command": "pytest"}, "exit_code: 0")
            )
            app.handle_turn_event(
                ToolCompleted("write", {"path": "b.py"}, "ERROR: denied")
            )
            await pilot.pause()

            tools = [content(widget) for widget in app.query(".tool-cell")]
            assert any("Explored" in item and "Read a.py" in item for item in tools)
            assert any("Ran pytest" in item for item in tools)
            assert "denied" in content(app.query_one(".error-cell", Static))

    asyncio.run(exercise())


def test_tui_context_command_does_not_call_provider(tmp_path: Path) -> None:
    def fail_provider(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("provider should not be called")

    async def exercise() -> None:
        app = make_app(
            tmp_path,
            provider=fail_provider,
            streaming_provider=fail_provider,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            app.query_one(Composer).load_text("/context")
            await pilot.press("enter")
            await pilot.pause()

            rendered = content(app.query_one(".context-cell", Static))
            assert "Context model: test/model" in rendered
            assert not app.active_turn

    asyncio.run(exercise())


def test_tui_manual_compaction_uses_existing_context_manager(tmp_path: Path) -> None:
    app = make_app(
        tmp_path,
        provider=lambda *args, **kwargs: response(text_message("Compact handoff")),
    )
    app.manager.conversation.append_user("Remember ALPHA")
    app.manager.conversation.append_model_round(
        [{"role": "assistant", "content": "old " + "x" * 160_000}]
    )
    app.manager.conversation.append_user("Continue with ALPHA")

    async def exercise() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            app.query_one(Composer).load_text("/compact")
            await pilot.press("enter")
            await pilot.pause(0.25)

            cells = [content(widget) for widget in app.query(".context-cell")]
            assert any("Compacted context" in cell for cell in cells)
            assert len(app.manager.conversation.checkpoints) == 1
            assert not app.active_turn

    asyncio.run(exercise())


def test_tui_escape_cancels_stream_and_removes_partial_tail(tmp_path: Path) -> None:
    def stream_provider(
        *args: Any,
        on_text_delta: Any,
        cancellation_token: Any,
        **kwargs: Any,
    ) -> Any:
        on_text_delta("partial")
        while not cancellation_token.cancelled:
            time.sleep(0.005)
        cancellation_token.raise_if_cancelled()

    async def exercise() -> None:
        app = make_app(tmp_path, streaming_provider=stream_provider)
        async with app.run_test(size=(80, 24)) as pilot:
            app.query_one(Composer).load_text("Wait")
            await pilot.press("enter")
            await pilot.pause(0.1)
            await pilot.press("escape")
            await pilot.pause(0.2)

            assert not app.active_turn
            assert not list(app.query(AssistantCell))
            notices = [content(widget) for widget in app.query(".notice-cell")]
            assert any("completed work was retained" in notice for notice in notices)

    asyncio.run(exercise())


def test_tui_submit_while_active_steers_and_continues_fifo(tmp_path: Path) -> None:
    calls = 0

    def stream_provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
        *,
        on_text_delta: Any,
        cancellation_token: Any,
    ) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            on_text_delta("obsolete")
            while not cancellation_token.cancelled:
                time.sleep(0.005)
            cancellation_token.raise_if_cancelled()
        on_text_delta("Steered answer")
        return response(text_message("Steered answer"))

    async def exercise() -> None:
        app = make_app(tmp_path, streaming_provider=stream_provider)
        async with app.run_test(size=(80, 24)) as pilot:
            composer = app.query_one(Composer)
            composer.load_text("Original")
            await pilot.press("enter")
            await pilot.pause(0.05)
            composer.load_text("New direction")
            await pilot.press("enter")
            await pilot.pause(0.3)

            assert not app.active_turn
            assert calls == 2
            assert app.manager.conversation.active_items()[0] == {
                "role": "user",
                "content": "Original",
            }
            assert app.manager.conversation.active_items()[1] == {
                "role": "user",
                "content": "New direction",
            }
            assert any(
                "applying queued input" in content(widget)
                for widget in app.query(".notice-cell")
            )
            assert any(
                cell.source_text == "Steered answer"
                for cell in app.query(AssistantCell)
            )

    asyncio.run(exercise())


def test_tui_stream_failure_removes_partial_tail_and_reports_rollback(
    tmp_path: Path,
) -> None:
    def stream_provider(*args: Any, on_text_delta: Any, **kwargs: Any) -> Any:
        on_text_delta("partial")
        raise RuntimeError("stream broke")

    async def exercise() -> None:
        app = make_app(tmp_path, streaming_provider=stream_provider)
        async with app.run_test(size=(80, 24)) as pilot:
            app.query_one(Composer).load_text("Fail")
            await pilot.press("enter")
            await pilot.pause(0.2)

            assert not list(app.query(AssistantCell))
            assert "stream broke" in content(app.query_one(".error-cell", Static))
            assert app.manager.conversation.active_items() == [
                {"role": "user", "content": "Fail"}
            ]

    asyncio.run(exercise())


def test_tui_passive_context_omits_footer_percentage(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    app.manager.budget = ContextBudget(None, "passive")

    async def exercise() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert content(app.query_one("#footer-right", Static)) == ""

    asyncio.run(exercise())


def test_tui_handles_supported_terminal_sizes(tmp_path: Path) -> None:
    async def exercise(size: tuple[int, int]) -> None:
        app = make_app(tmp_path)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert app.query_one(Composer).is_mounted
            assert app.query_one("#transcript").is_mounted

    for size in ((120, 40), (80, 24), (40, 10)):
        asyncio.run(exercise(size))


def test_tui_shift_enter_inserts_newline_without_submitting(tmp_path: Path) -> None:
    async def exercise() -> None:
        app = make_app(tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            composer = app.query_one(Composer)
            await pilot.press("f", "i", "r", "s", "t")
            await pilot.press("shift+enter")
            await pilot.press("s", "e", "c", "o", "n", "d")
            await pilot.pause()

            assert composer.text == "first\nsecond"
            assert not app.active_turn

    asyncio.run(exercise())
