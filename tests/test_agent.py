import json
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
