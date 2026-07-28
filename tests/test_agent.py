import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import coding_kid.agent as agent_module
from coding_kid.agent import MAX_TOOL_CALLS_PER_TURN, SYSTEM_PROMPT, run_turn
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
    assert provider_calls[0][0] == SYSTEM_PROMPT
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
    assert provider_instructions[0] == SYSTEM_PROMPT
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
    assert provider_instructions[:2] == [SYSTEM_PROMPT, SYSTEM_PROMPT]
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


def test_system_prompt_describes_the_runtime() -> None:
    assert str(Path.cwd()) in SYSTEM_PROMPT
    assert "OPENROUTER_MODEL" in SYSTEM_PROMPT
    assert "cmd.exe" in SYSTEM_PROMPT
    assert "only call the tools provided" in SYSTEM_PROMPT.lower()
    assert "recursive tree commands" in SYSTEM_PROMPT.lower()
    assert 'use "."' in SYSTEM_PROMPT.lower()
    assert "use the fewest tool calls" in SYSTEM_PROMPT.lower()
    assert "every file" in SYSTEM_PROMPT.lower()
    assert "run tests" in SYSTEM_PROMPT.lower()
    assert "todo tool" in SYSTEM_PROMPT.lower()
    assert "in_progress" in SYSTEM_PROMPT
    assert "execution schedule" in SYSTEM_PROMPT.lower()
    assert "first 6 file or shell calls" in SYSTEM_PROMPT.lower()
    assert "reserve at least 2 calls" in SYSTEM_PROMPT.lower()


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
    assert provider_instructions[0] == SYSTEM_PROMPT
    assert "Current todos:" in provider_instructions[1]
    assert "[in_progress] Write hello.txt" in provider_instructions[1]
    assert "Todo reconciliation required:" in provider_instructions[3]
    assert get_todos() == []
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello"


def test_run_turn_rejects_a_second_final_answer_with_an_active_todo() -> None:
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

    with pytest.raises(RuntimeError, match="todo still in_progress"):
        run_turn(messages, lambda instructions, messages, tools: next(responses))

    assert messages == [{"role": "user", "content": "Finish the work"}]


def test_run_turn_preserves_pending_todos_for_a_later_turn() -> None:
    agent_module.dispatch_tool(
        "todo",
        {"todos": [{"content": "Continue later", "status": "pending"}]},
    )
    response = SimpleNamespace(output=[text_message("The remaining step is pending.")])

    answer = run_turn(
        [{"role": "user", "content": "Pause here"}],
        lambda instructions, messages, tools: response,
    )

    assert answer == "The remaining step is pending."
    assert get_todos() == [{"content": "Continue later", "status": "pending"}]
