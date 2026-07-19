import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import coding_kid.agent as agent_module
from coding_kid.agent import SYSTEM_PROMPT, run_turn


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
    provider_calls = 0

    def sometimes_empty_provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
    ) -> SimpleNamespace:
        nonlocal provider_calls
        provider_calls += 1
        return next(responses)

    answer = run_turn([], sometimes_empty_provider)

    assert answer == "Recovered answer."
    assert provider_calls == 2


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
    provider_calls = 0

    def provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
    ) -> SimpleNamespace:
        nonlocal provider_calls
        provider_calls += 1
        return next(responses)

    monkeypatch.setattr(agent_module, "dispatch_tool", lambda name, arguments: "files")

    answer = run_turn([], provider)

    assert answer == "Directory described."
    assert provider_calls == 3


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
