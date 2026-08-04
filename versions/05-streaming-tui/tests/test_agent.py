import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import coding_kid.agent as agent_module
from coding_kid.agent import (
    MAX_TOOL_CALLS_PER_TURN,
    SYSTEM_PROMPT,
    current_instructions,
    run_turn,
)
from coding_kid.context import ProjectInstruction, SessionContext
from coding_kid.events import (
    AssistantMessageCompleted,
    AssistantTextDelta,
    CancellationToken,
    TodoUpdated,
    ToolCompleted,
    ToolStarted,
    TurnCancelled,
    TurnCompleted,
    TurnInterrupted,
    TurnStarted,
)
from coding_kid.tools import get_todos


def tool_call(call_id: str, name: str, arguments: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        type="function_call",
        call_id=call_id,
        name=name,
        arguments=json.dumps(arguments),
    )


def text_message(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="message",
        content=[SimpleNamespace(type="output_text", text=text)],
    )


def test_run_turn_executes_multiple_tools_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            SimpleNamespace(
                output=[
                    tool_call("call-1", "read", {"path": "one.py"}),
                    tool_call("call-2", "write", {"path": "two.py", "content": "x"}),
                ]
            ),
            SimpleNamespace(output=[text_message("Finished.")]),
        ]
    )
    provider_calls: list[tuple[str, list[Any], list[dict[str, Any]]]] = []
    executed: list[tuple[str, dict[str, Any]]] = []
    observed: list[tuple[str, str]] = []

    def fake_provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
    ) -> SimpleNamespace:
        provider_calls.append((instructions, list(messages), tools))
        return next(responses)

    def fake_dispatch(name: str, arguments: dict[str, Any]) -> str:
        executed.append((name, arguments))
        return f"result from {name}"

    monkeypatch.setattr(agent_module, "dispatch_tool", fake_dispatch)
    messages: list[Any] = [{"role": "user", "content": "Make the change"}]

    final_text = run_turn(
        messages,
        fake_provider,
        on_tool=lambda name, arguments, result: observed.append((name, result)),
    )

    assert final_text == "Finished."
    assert [name for name, _ in executed] == ["read", "write"]
    assert observed == [
        ("read", "result from read"),
        ("write", "result from write"),
    ]
    assert len(provider_calls) == 2
    assert provider_calls[0][0].startswith(SYSTEM_PROMPT)
    assert "Runtime environment:" in provider_calls[0][0]
    assert [item["name"] for item in provider_calls[0][2]][:2] == ["execute", "read"]
    tool_outputs = [
        item
        for item in messages
        if isinstance(item, dict) and item.get("type") == "function_call_output"
    ]
    assert tool_outputs == [
        {
            "type": "function_call_output",
            "call_id": "call-1",
            "output": "result from read",
        },
        {
            "type": "function_call_output",
            "call_id": "call-2",
            "output": "result from write",
        },
    ]
    second_request = provider_calls[1][1]
    assert second_request[-2]["call_id"] == "call-1"
    assert second_request[-1]["call_id"] == "call-2"


def test_run_turn_streams_text_and_emits_typed_tool_and_todo_events() -> None:
    responses = iter(
        [
            SimpleNamespace(
                output=[
                    tool_call(
                        "todo-1",
                        "todo",
                        {
                            "todos": [
                                {"content": "Inspect", "status": "completed"},
                                {"content": "Finish", "status": "in_progress"},
                            ]
                        },
                    )
                ]
            ),
            SimpleNamespace(
                output=[
                    tool_call(
                        "todo-2",
                        "todo",
                        {
                            "todos": [
                                {"content": "Inspect", "status": "completed"},
                                {"content": "Finish", "status": "completed"},
                            ]
                        },
                    )
                ]
            ),
            SimpleNamespace(output=[text_message("Finished.")]),
        ]
    )
    events: list[Any] = []

    def stream_provider(*args: Any, on_text_delta: Any, **kwargs: Any) -> Any:
        response = next(responses)
        if any(item.type == "message" for item in response.output):
            on_text_delta("Fin")
            on_text_delta("ished.")
        return response

    answer = run_turn(
        [],
        lambda *args, **kwargs: pytest.fail("non-stream provider called"),
        stream_provider=stream_provider,
        event_sink=events.append,
    )

    assert answer == "Finished."
    assert isinstance(events[0], TurnStarted)
    assert [
        event.delta for event in events if isinstance(event, AssistantTextDelta)
    ] == [
        "Fin",
        "ished.",
    ]
    assert len([event for event in events if isinstance(event, ToolStarted)]) == 2
    assert len([event for event in events if isinstance(event, ToolCompleted)]) == 2
    todo_events = [event for event in events if isinstance(event, TodoUpdated)]
    assert [item.status for item in todo_events[0].items] == [
        "completed",
        "in_progress",
    ]
    assert isinstance(events[-2], AssistantMessageCompleted)
    assert events[-2].text == "Finished."
    assert isinstance(events[-1], TurnCompleted)


def test_run_turn_stream_cancellation_emits_interrupt_and_keeps_history() -> None:
    token = CancellationToken()
    events: list[Any] = []
    messages: list[Any] = [{"role": "user", "content": "Keep me"}]

    def stream_provider(*args: Any, on_text_delta: Any, **kwargs: Any) -> Any:
        on_text_delta("partial")
        token.cancel()
        token.raise_if_cancelled()

    with pytest.raises(TurnCancelled):
        run_turn(
            messages,
            lambda *args, **kwargs: pytest.fail("non-stream provider called"),
            stream_provider=stream_provider,
            event_sink=events.append,
            cancellation_token=token,
        )

    assert messages == [{"role": "user", "content": "Keep me"}]
    assert isinstance(events[0], TurnStarted)
    assert isinstance(events[1], AssistantTextDelta)
    assert isinstance(events[-1], TurnInterrupted)


def test_run_turn_stops_after_maximum_steps() -> None:
    def endless_provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
    ) -> SimpleNamespace:
        return SimpleNamespace(output=[tool_call("again", "read", {"path": "x"})])

    with pytest.raises(RuntimeError, match="maximum"):
        run_turn([], endless_provider, max_steps=2)


def test_run_turn_stops_executing_tools_at_the_per_turn_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_calls = [
        tool_call(f"call-{number}", "read", {"path": f"file-{number}.py"})
        for number in range(MAX_TOOL_CALLS_PER_TURN + 3)
    ]
    responses = iter(
        [
            SimpleNamespace(output=requested_calls),
            SimpleNamespace(output=[text_message("Enough evidence.")]),
        ]
    )
    executed: list[str] = []
    observed: list[str] = []
    provider_inputs: list[tuple[str, list[Any]]] = []

    def provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
    ) -> SimpleNamespace:
        provider_inputs.append((instructions, list(messages)))
        return next(responses)

    def dispatch(name: str, arguments: dict[str, Any]) -> str:
        executed.append(arguments["path"])
        return "read result"

    monkeypatch.setattr(agent_module, "dispatch_tool", dispatch)

    answer = run_turn(
        [],
        provider,
        on_tool=lambda name, arguments, result: observed.append(arguments["path"]),
    )

    assert answer == "Enough evidence."
    assert len(executed) == MAX_TOOL_CALLS_PER_TURN
    assert observed == executed
    assert "tool-call budget" in provider_inputs[1][0].lower()
    skipped_outputs = [
        item["output"]
        for item in provider_inputs[1][1]
        if isinstance(item, dict)
        and item.get("type") == "function_call_output"
        and item["output"].startswith("Tool call skipped")
    ]
    assert len(skipped_outputs) == 3


def test_run_turn_does_not_count_todo_against_the_tool_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_calls = [
        tool_call(
            "todo-1",
            "todo",
            {
                "todos": [
                    {"content": "Read files", "status": "in_progress"},
                    {"content": "Answer", "status": "pending"},
                ]
            },
        ),
        *[
            tool_call(f"call-{number}", "read", {"path": f"file-{number}.py"})
            for number in range(MAX_TOOL_CALLS_PER_TURN)
        ],
        tool_call(
            "todo-2",
            "todo",
            {
                "todos": [
                    {"content": "Read files", "status": "completed"},
                    {"content": "Answer", "status": "in_progress"},
                ]
            },
        ),
    ]
    responses = iter(
        [
            SimpleNamespace(output=requested_calls),
            SimpleNamespace(output=[text_message("Budget reserved for real work.")]),
        ]
    )
    executed: list[str] = []

    def provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
    ) -> SimpleNamespace:
        return next(responses)

    def dispatch(name: str, arguments: dict[str, Any]) -> str:
        executed.append(name)
        if name == "todo":
            return "Updated todos"
        return "read result"

    monkeypatch.setattr(agent_module, "dispatch_tool", dispatch)

    answer = run_turn([], provider)

    assert answer == "Budget reserved for real work."
    assert executed.count("todo") == 2
    assert executed.count("read") == MAX_TOOL_CALLS_PER_TURN


def test_run_turn_retries_one_empty_model_response() -> None:
    responses = iter(
        [
            SimpleNamespace(output=[SimpleNamespace(type="reasoning")], output_text=""),
            SimpleNamespace(
                output=[text_message("Recovered answer.")],
                output_text="Recovered answer.",
            ),
        ]
    )
    provider_instructions: list[str] = []

    def sometimes_empty_provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
    ) -> SimpleNamespace:
        provider_instructions.append(instructions)
        return next(responses)

    answer = run_turn([], sometimes_empty_provider)

    assert answer == "Recovered answer."
    assert len(provider_instructions) == 2
    assert provider_instructions[0].startswith(SYSTEM_PROMPT)
    assert "previous response was empty" in provider_instructions[1].lower()
    assert "answer the user now" in provider_instructions[1].lower()


def test_run_turn_recovers_from_an_empty_response_after_a_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            SimpleNamespace(
                output=[tool_call("call-1", "execute", {"command": "dir"})]
            ),
            SimpleNamespace(output=[SimpleNamespace(type="reasoning")], output_text=""),
            SimpleNamespace(
                output=[text_message("Directory described.")],
                output_text="Directory described.",
            ),
        ]
    )
    provider_instructions: list[str] = []

    def provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
    ) -> SimpleNamespace:
        provider_instructions.append(instructions)
        return next(responses)

    monkeypatch.setattr(agent_module, "dispatch_tool", lambda name, arguments: "files")

    answer = run_turn([], provider)

    assert answer == "Directory described."
    assert len(provider_instructions) == 3
    assert provider_instructions[0] == provider_instructions[1]
    assert provider_instructions[0].startswith(SYSTEM_PROMPT)
    assert "answer the user now" in provider_instructions[2].lower()


def test_run_turn_recovers_after_an_unknown_tool_call() -> None:
    responses = iter(
        [
            SimpleNamespace(output=[tool_call("call-1", "print_tree", {"path": "."})]),
            SimpleNamespace(output=[text_message("Repository understood.")]),
        ]
    )
    observed: list[tuple[str, str]] = []

    answer = run_turn(
        [],
        lambda instructions, messages, tools: next(responses),
        on_tool=lambda name, arguments, result: observed.append((name, result)),
    )

    assert answer == "Repository understood."
    assert observed == [("print_tree", "ERROR: Unknown tool: print_tree")]


def test_run_turn_rejects_repeated_empty_model_responses() -> None:
    def empty_provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
    ) -> SimpleNamespace:
        return SimpleNamespace(
            output=[SimpleNamespace(type="reasoning")], output_text=""
        )

    with pytest.raises(RuntimeError, match="empty"):
        run_turn([], empty_provider)


def test_run_turn_does_not_commit_partial_history_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            SimpleNamespace(output=[tool_call("call-1", "read", {"path": "one.py"})]),
            RuntimeError("provider failed"),
        ]
    )

    def failing_provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
    ) -> SimpleNamespace:
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(agent_module, "dispatch_tool", lambda name, arguments: "ok")
    messages: list[Any] = [{"role": "user", "content": "Inspect one.py"}]

    with pytest.raises(RuntimeError, match="provider failed"):
        run_turn(messages, failing_provider)

    assert messages == [{"role": "user", "content": "Inspect one.py"}]


def test_run_turn_injects_cached_project_context_without_storing_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            SimpleNamespace(
                output=[tool_call("call-1", "read", {"path": "module.py"})]
            ),
            SimpleNamespace(output=[text_message("Finished.")]),
        ]
    )
    provider_inputs: list[list[Any]] = []
    session_context = SessionContext(
        cwd=tmp_path,
        operating_system="Windows 11",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-07-30",
        project_root=tmp_path,
        project_instructions=(
            ProjectInstruction(tmp_path / "AGENTS.md", "Always run pytest."),
        ),
    )

    def provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
    ) -> SimpleNamespace:
        provider_inputs.append(list(messages))
        return next(responses)

    monkeypatch.setattr(agent_module, "dispatch_tool", lambda name, arguments: "ok")
    messages: list[Any] = [{"role": "user", "content": "Fix module.py"}]

    answer = run_turn(messages, provider, session_context=session_context)

    assert answer == "Finished."
    assert len(provider_inputs) == 2
    assert all(
        "Always run pytest." in request[0]["content"] for request in provider_inputs
    )
    assert all(request.count(provider_inputs[0][0]) == 1 for request in provider_inputs)
    assert messages[0] == {"role": "user", "content": "Fix module.py"}
    assert all(
        not (
            isinstance(item, dict)
            and item.get("role") == "user"
            and "Always run pytest." in item.get("content", "")
        )
        for item in messages
    )


def test_system_prompt_describes_the_runtime() -> None:
    session_context = SessionContext.capture()
    instructions = current_instructions(session_context)

    assert str(session_context.cwd) in instructions
    assert "OPENROUTER_MODEL" in instructions
    assert "cmd.exe" in instructions
    assert "only call the tools provided" in SYSTEM_PROMPT.lower()
    assert "recursive tree commands" in SYSTEM_PROMPT.lower()
    assert 'use "."' in SYSTEM_PROMPT.lower()
    assert "use the fewest tool calls" in SYSTEM_PROMPT.lower()
    assert "every file" in SYSTEM_PROMPT.lower()
    assert "run tests" in SYSTEM_PROMPT.lower()
    assert "todo tool" in SYSTEM_PROMPT.lower()
    assert "in_progress" in SYSTEM_PROMPT


def test_run_turn_uses_todo_and_injects_current_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            SimpleNamespace(
                output=[
                    tool_call(
                        "call-1",
                        "todo",
                        {
                            "todos": [
                                {
                                    "content": "Write hello.txt",
                                    "status": "in_progress",
                                },
                                {
                                    "content": "Confirm contents",
                                    "status": "pending",
                                },
                            ]
                        },
                    )
                ]
            ),
            SimpleNamespace(
                output=[
                    tool_call(
                        "call-2",
                        "write",
                        {"path": "hello.txt", "content": "hello"},
                    )
                ]
            ),
            SimpleNamespace(output=[text_message("I think the work is finished.")]),
            SimpleNamespace(
                output=[
                    tool_call(
                        "call-3",
                        "todo",
                        {
                            "todos": [
                                {
                                    "content": "Write hello.txt",
                                    "status": "completed",
                                },
                                {
                                    "content": "Confirm contents",
                                    "status": "completed",
                                },
                            ]
                        },
                    )
                ]
            ),
            SimpleNamespace(output=[text_message("Todo-driven work finished.")]),
        ]
    )
    provider_instructions: list[str] = []

    def provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
    ) -> SimpleNamespace:
        provider_instructions.append(instructions)
        assert any(tool["name"] == "todo" for tool in tools)
        return next(responses)

    monkeypatch.chdir(tmp_path)
    answer = run_turn([{"role": "user", "content": "Do the two steps"}], provider)

    assert answer == "Todo-driven work finished."
    assert provider_instructions[0].startswith(SYSTEM_PROMPT)
    assert "Current todos:" in provider_instructions[1]
    assert "[in_progress] Write hello.txt" in provider_instructions[1]
    assert "Todo reconciliation required:" in provider_instructions[3]
    assert get_todos() == []
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello"


def test_run_turn_rejects_a_second_final_answer_with_an_incomplete_todo() -> None:
    responses = iter(
        [
            SimpleNamespace(
                output=[
                    tool_call(
                        "call-1",
                        "todo",
                        {
                            "todos": [
                                {"content": "Finish work", "status": "in_progress"}
                            ]
                        },
                    )
                ]
            ),
            SimpleNamespace(output=[text_message("Finished.")]),
            SimpleNamespace(output=[text_message("Still finished.")]),
        ]
    )
    messages = [{"role": "user", "content": "Finish the work"}]

    with pytest.raises(RuntimeError, match="unfinished todos"):
        run_turn(messages, lambda instructions, messages, tools: next(responses))

    assert messages == [{"role": "user", "content": "Finish the work"}]


def test_run_turn_requires_pending_todos_to_be_completed_before_final() -> None:
    agent_module.dispatch_tool(
        "todo",
        {"todos": [{"content": "Continue later", "status": "pending"}]},
    )
    responses = iter(
        [
            SimpleNamespace(output=[text_message("The remaining step is pending.")]),
            SimpleNamespace(
                output=[
                    tool_call(
                        "call-1",
                        "todo",
                        {
                            "todos": [
                                {"content": "Continue later", "status": "completed"}
                            ]
                        },
                    )
                ]
            ),
            SimpleNamespace(output=[text_message("The remaining step is complete.")]),
        ]
    )
    provider_instructions: list[str] = []

    answer = run_turn(
        [{"role": "user", "content": "Pause here"}],
        lambda instructions, messages, tools: (
            provider_instructions.append(instructions) or next(responses)
        ),
    )

    assert answer == "The remaining step is complete."
    assert "Todo reconciliation required:" in provider_instructions[1]
    assert get_todos() == []
