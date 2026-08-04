from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from textual.widgets import Static

from coding_kid.context import SessionContext
from coding_kid.context_manager import ContextBudget, ContextManager
from coding_kid.events import ToolCompleted
from coding_kid.memory import MemoryManager
from coding_kid.sessions import SessionStore
from coding_kid.tui import AssistantCell, CodingKidApp, Composer


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
        [{"role": "assistant", "content": "old " + "x" * 30_000}]
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
            assert any("state restored" in notice for notice in notices)

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
            assert app.manager.conversation.transcript == []

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
