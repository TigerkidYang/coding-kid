import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from typing import Any

import pytest

import coding_kid.agent as agent_module
from coding_kid.background_tasks import BackgroundTaskManager
from coding_kid.agent import (
    MAX_TOOL_CALLS_PER_TURN,
    SYSTEM_PROMPT,
    current_instructions,
    run_turn,
)
from coding_kid.context import ProjectInstruction, SessionContext
from coding_kid.context_manager import ContextBudget, ContextManager
from coding_kid.events import (
    AssistantMessageCompleted,
    AssistantTextDelta,
    AssistantStreamReset,
    CancellationToken,
    TodoUpdated,
    TodoCompletionDeferred,
    ToolCompleted,
    ToolStarted,
    TurnCancelled,
    TurnCompleted,
    TurnInterrupted,
    TurnStarted,
    RetryScheduled,
)
from coding_kid.provider import ProviderIncompleteError, ProviderProtocolError
from coding_kid.tools import ToolRegistry, build_tool_registry, get_todos
from coding_kid.turn_control import TurnLimits


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


def test_run_turn_injects_request_only_memory_and_records_valid_citations(
    tmp_path: Path,
) -> None:
    context = SessionContext(
        cwd=tmp_path,
        operating_system="Test OS",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-08-04",
        project_root=tmp_path,
        project_instructions=(),
    )
    manager = ContextManager(context, ContextBudget(32_768, "test"))
    manager.conversation.append_user("Apply ALPHA")
    calls: list[list[Any]] = []
    citations: list[tuple[str, ...]] = []

    def provider(instructions: str, messages: list[Any], tools: list[Any]) -> Any:
        calls.append(messages)
        return SimpleNamespace(
            output=[
                text_message(
                    "Applied.\n"
                    '<coding_kid_memory_citations>["memory-1"]'
                    "</coding_kid_memory_citations>"
                )
            ],
            usage=None,
        )

    answer = run_turn(
        manager,
        provider,
        request_context=[{"role": "user", "content": "memory-1: Use ALPHA"}],
        on_memory_citations=citations.append,
    )

    assert calls[0][0]["content"] == "memory-1: Use ALPHA"
    assert answer == "Applied."
    assert citations == [("memory-1",)]
    assert "coding_kid_memory_citations" not in str(
        manager.conversation.transcript[-1].items
    )
    assert all(
        "memory-1: Use ALPHA" not in str(segment.items)
        for segment in manager.conversation.transcript
    )


def test_memory_usage_tracking_failure_does_not_fail_turn(tmp_path: Path) -> None:
    context = SessionContext(
        cwd=tmp_path,
        operating_system="Test OS",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-08-04",
        project_root=tmp_path,
        project_instructions=(),
    )
    manager = ContextManager(context, ContextBudget(32_768, "test"))
    manager.conversation.append_user("Apply ALPHA")

    answer = run_turn(
        manager,
        lambda *args, **kwargs: SimpleNamespace(
            output=[
                text_message(
                    "Done.\n"
                    '<coding_kid_memory_citations>["memory-1"]'
                    "</coding_kid_memory_citations>"
                )
            ],
            usage=None,
        ),
        on_memory_citations=lambda cited: (_ for _ in ()).throw(OSError("disk")),
    )

    assert answer == "Done."


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


def test_run_turn_overlaps_explicitly_safe_tools_and_orders_results() -> None:
    barrier = threading.Barrier(2)
    active = 0
    maximum_active = 0
    lock = threading.Lock()

    def safe_read(path: str) -> str:
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        try:
            barrier.wait(timeout=2)
            return f"read {path}"
        finally:
            with lock:
                active -= 1

    registry = ToolRegistry(
        {
            "safe_read": {
                "description": "Test-only safe read.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
                "function": safe_read,
                "parallel_safe": True,
            }
        }
    )
    responses = iter(
        [
            SimpleNamespace(
                output=[
                    tool_call("call-1", "safe_read", {"path": "one"}),
                    tool_call("call-2", "safe_read", {"path": "two"}),
                ]
            ),
            SimpleNamespace(output=[text_message("Finished.")]),
        ]
    )
    requests: list[list[Any]] = []

    def provider(*args: Any, **kwargs: Any) -> Any:
        requests.append(list(args[1]))
        return next(responses)

    assert run_turn([], provider, tool_registry=registry) == "Finished."
    assert maximum_active == 2
    outputs = [
        item
        for item in requests[1]
        if isinstance(item, dict) and item.get("type") == "function_call_output"
    ]
    assert [item["call_id"] for item in outputs] == ["call-1", "call-2"]
    assert [item["output"] for item in outputs] == ["read one", "read two"]


def test_run_turn_keeps_exclusive_tools_between_safe_batches() -> None:
    order: list[str] = []

    def record(label: str) -> str:
        order.append(label)
        return label

    schema = {
        "type": "object",
        "properties": {"label": {"type": "string"}},
        "required": ["label"],
        "additionalProperties": False,
    }
    registry = ToolRegistry(
        {
            "safe": {
                "description": "Test-only safe operation.",
                "parameters": schema,
                "function": record,
                "parallel_safe": True,
            },
            "exclusive": {
                "description": "Test-only exclusive operation.",
                "parameters": schema,
                "function": record,
            },
        }
    )
    responses = iter(
        [
            SimpleNamespace(
                output=[
                    tool_call("call-1", "safe", {"label": "safe one"}),
                    tool_call("call-2", "exclusive", {"label": "exclusive"}),
                    tool_call("call-3", "safe", {"label": "safe two"}),
                ]
            ),
            SimpleNamespace(output=[text_message("Finished.")]),
        ]
    )

    assert (
        run_turn([], lambda *args, **kwargs: next(responses), tool_registry=registry)
        == "Finished."
    )
    assert order == ["safe one", "exclusive", "safe two"]


def test_run_turn_completes_background_work_protocol(tmp_path: Path) -> None:
    worker = tmp_path / "worker.py"
    evidence = tmp_path / "evidence.txt"
    worker.write_text(
        "import time\nprint('ready', flush=True)\ntime.sleep(0.2)\nprint('done')\n",
        encoding="utf-8",
    )
    evidence.write_text("independent", encoding="utf-8")
    manager = BackgroundTaskManager(id_factory=lambda: "task_agent")
    registry = build_tool_registry(manager)
    responses = iter(
        [
            SimpleNamespace(
                output=[
                    tool_call(
                        "launch",
                        "execute",
                        {
                            "command": f'& "{sys.executable}" "{worker}"',
                            "background": True,
                        },
                    )
                ]
            ),
            SimpleNamespace(
                output=[tool_call("read", "read", {"path": str(evidence)})]
            ),
            SimpleNamespace(
                output=[
                    tool_call(
                        "wait",
                        "task",
                        {
                            "action": "wait",
                            "task_id": "task_agent",
                            "timeout_seconds": 10,
                        },
                    )
                ]
            ),
            SimpleNamespace(output=[text_message("Used the completed result.")]),
        ]
    )
    instructions: list[str] = []

    def provider(prompt: str, messages: list[Any], tools: list[Any]) -> Any:
        instructions.append(prompt)
        return next(responses)

    try:
        answer = run_turn(
            [],
            provider,
            tool_registry=registry,
            background_tasks=manager,
        )
    finally:
        manager.close()

    assert answer == "Used the completed result."
    assert any("task_agent: running" in prompt for prompt in instructions[1:])
    assert any("task_agent: completed" in prompt for prompt in instructions[1:])


def test_failed_turn_keeps_launched_background_task_discoverable(
    tmp_path: Path,
) -> None:
    worker = tmp_path / "slow.py"
    worker.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    manager = BackgroundTaskManager(id_factory=lambda: "task_survives")
    registry = build_tool_registry(manager)
    responses = iter(
        [
            SimpleNamespace(
                output=[
                    tool_call(
                        "launch",
                        "execute",
                        {
                            "command": f'& "{sys.executable}" "{worker}"',
                            "background": True,
                        },
                    )
                ]
            ),
            RuntimeError("provider failed"),
        ]
    )

    def failing_provider(*args: Any) -> Any:
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    conversation: list[Any] = []
    try:
        with pytest.raises(RuntimeError, match="provider failed"):
            run_turn(
                conversation,
                failing_provider,
                tool_registry=registry,
                background_tasks=manager,
            )
        assert conversation == []
        assert manager.poll("task_survives").status == "running"

        prompts: list[str] = []
        answer = run_turn(
            conversation,
            lambda prompt, *args: (
                prompts.append(prompt)
                or SimpleNamespace(output=[text_message("Recovered.")])
            ),
            tool_registry=build_tool_registry(manager),
            background_tasks=manager,
        )
        assert answer == "Recovered."
        assert "task_survives: running" in prompts[0]
    finally:
        manager.close()


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
    completed_messages = [
        event for event in events if isinstance(event, AssistantMessageCompleted)
    ]
    assert completed_messages[-1].text == "Finished."
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
    assert any(isinstance(event, AssistantTextDelta) for event in events)
    assert isinstance(events[-1], TurnInterrupted)


def test_run_turn_stops_after_maximum_steps() -> None:
    def endless_provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
    ) -> SimpleNamespace:
        return SimpleNamespace(output=[tool_call("again", "read", {"path": "x"})])

    messages: list[Any] = []
    answer = run_turn(messages, endless_provider, max_steps=2)

    assert "configured model/tool step boundary" in answer
    assert any(
        isinstance(item, dict)
        and item.get("type") == "message"
        and "configured model/tool step boundary" in str(item)
        for item in messages
    )


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


def test_run_turn_retries_transient_provider_failure_observably(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    events: list[Any] = []

    class TransientError(RuntimeError):
        status_code = 503

    def provider(instructions: str, messages: list[Any], tools: list[Any]) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TransientError("temporary")
        return SimpleNamespace(output=[text_message("Recovered")], usage=None)

    monkeypatch.setattr(agent_module, "provider_retry_delay", lambda error, attempt: 0)

    assert run_turn([], provider, event_sink=events.append) == "Recovered"
    assert calls == 2
    assert len([event for event in events if isinstance(event, RetryScheduled)]) == 1
    assert any(isinstance(event, AssistantStreamReset) for event in events)


def test_run_turn_retries_provider_protocol_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def provider(instructions: str, messages: list[Any], tools: list[Any]) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ProviderProtocolError("null collection")
        return SimpleNamespace(output=[text_message("Recovered")], usage=None)

    monkeypatch.setattr(agent_module, "provider_retry_delay", lambda error, attempt: 0)

    assert run_turn([], provider) == "Recovered"
    assert calls == 2


def test_run_turn_resumes_completed_tool_round_after_raw_null_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executions: list[str] = []
    requests: list[list[Any]] = []
    calls = 0
    registry = ToolRegistry(
        {
            "record": {
                "description": "Record one test value.",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                "function": lambda value: executions.append(value) or "recorded",
            }
        }
    )

    def provider(instructions: str, messages: list[Any], tools: list[Any]) -> Any:
        nonlocal calls
        calls += 1
        requests.append(list(messages))
        if calls == 1:
            return SimpleNamespace(
                output=[tool_call("call-1", "record", {"value": "once"})],
                usage=None,
            )
        if calls == 2:
            raise TypeError("'NoneType' object is not iterable")
        return SimpleNamespace(output=[text_message("Recovered round")], usage=None)

    monkeypatch.setattr(agent_module.time, "sleep", lambda _: None)

    assert run_turn([], provider, tool_registry=registry) == "Recovered round"
    assert executions == ["once"]
    assert calls == 3
    assert any(
        isinstance(item, dict)
        and item.get("type") == "function_call_output"
        and item.get("call_id") == "call-1"
        for item in requests[2]
    )


def test_run_turn_omits_empty_provider_messages_before_tool_followup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def provider(instructions: str, messages: list[Any], tools: list[Any]) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            return SimpleNamespace(
                output=[
                    SimpleNamespace(type="message", role="assistant", content=None),
                    tool_call("call-1", "read", {"path": "module.py"}),
                ],
                usage=None,
            )
        empty_messages = [
            item
            for item in messages
            if isinstance(item, dict)
            and item.get("type") == "message"
            and not item.get("content")
        ]
        assert empty_messages == []
        return SimpleNamespace(output=[text_message("Finished")], usage=None)

    monkeypatch.setattr(agent_module, "dispatch_tool", lambda name, arguments: "ok")

    assert run_turn([], provider) == "Finished"


def test_run_turn_recovers_from_output_limit_twice() -> None:
    calls = 0
    seen_instructions: list[str] = []

    def provider(instructions: str, messages: list[Any], tools: list[Any]) -> Any:
        nonlocal calls
        calls += 1
        seen_instructions.append(instructions)
        if calls < 3:
            raise ProviderIncompleteError("max_output_tokens")
        return SimpleNamespace(output=[text_message("Finished")], usage=None)

    assert run_turn([], provider) == "Finished"
    assert calls == 3
    assert "Output limit recovery" in seen_instructions[-1]


def test_run_turn_enforces_shared_recovery_budget() -> None:
    def provider(instructions: str, messages: list[Any], tools: list[Any]) -> Any:
        raise ProviderIncompleteError("max_output_tokens")

    answer = run_turn([], provider, limits=TurnLimits(max_recoveries=1))

    assert "recovery budget exhausted" in answer
    assert "may be resumed" in answer


def test_run_turn_stops_repeated_identical_tool_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    advertised_tool_counts: list[int] = []

    def provider(instructions: str, messages: list[Any], tools: list[Any]) -> Any:
        nonlocal calls
        calls += 1
        advertised_tool_counts.append(len(tools))
        if calls <= 4:
            return SimpleNamespace(
                output=[tool_call(f"call-{calls}", "read", {"path": "same.txt"})],
                usage=None,
            )
        return SimpleNamespace(
            output=[text_message("Stopped with evidence")], usage=None
        )

    monkeypatch.setattr(agent_module, "dispatch_tool", lambda name, arguments: "same")

    assert run_turn([], provider) == "Stopped with evidence"
    assert advertised_tool_counts[-1] == 0


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

    answer = run_turn([], empty_provider)
    assert "repeated empty responses" in answer


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
    assert "PowerShell" in instructions
    assert "only call the tools provided" in SYSTEM_PROMPT.lower()
    assert "recursive tree commands" in SYSTEM_PROMPT.lower()
    assert 'use "."' in SYSTEM_PROMPT.lower()
    assert "use the fewest tool calls" in SYSTEM_PROMPT.lower()
    assert "every file" in SYSTEM_PROMPT.lower()
    assert "run tests" in SYSTEM_PROMPT.lower()
    assert "todo tool" in SYSTEM_PROMPT.lower()
    assert "in_progress" in SYSTEM_PROMPT
    assert "authoritative evidence" in SYSTEM_PROMPT.lower()


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
    assert "Todo reconciliation suggestion:" in provider_instructions[3]
    assert get_todos() == []
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello"


def test_run_turn_accepts_second_final_after_one_soft_in_progress_reminder() -> None:
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
    todo_state = agent_module.TodoState()
    events: list[Any] = []

    answer = run_turn(
        messages,
        lambda instructions, messages, tools: next(responses),
        todo_state=todo_state,
        tool_registry=build_tool_registry(todo_state=todo_state),
        event_sink=events.append,
    )

    assert answer == "Still finished."
    assert todo_state.items == [{"content": "Finish work", "status": "in_progress"}]
    deferred = [event for event in events if isinstance(event, TodoCompletionDeferred)]
    assert len(deferred) == 1
    assert deferred[0].reminder_sent is True


def test_run_turn_allows_pending_todo_to_end_without_a_retry() -> None:
    todo_state = agent_module.TodoState(
        [{"content": "Continue later", "status": "pending"}]
    )
    response = SimpleNamespace(output=[text_message("The remaining step is pending.")])
    provider_instructions: list[str] = []
    events: list[Any] = []

    answer = run_turn(
        [{"role": "user", "content": "Pause here"}],
        lambda instructions, messages, tools: (
            provider_instructions.append(instructions) or response
        ),
        todo_state=todo_state,
        event_sink=events.append,
    )

    assert answer == "The remaining step is pending."
    assert len(provider_instructions) == 1
    assert todo_state.items == [{"content": "Continue later", "status": "pending"}]
    deferred = [event for event in events if isinstance(event, TodoCompletionDeferred)]
    assert len(deferred) == 1
    assert deferred[0].reminder_sent is False
