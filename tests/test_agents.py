from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import threading
import time
from typing import Any

import pytest

from coding_kid.agents import AgentError, AgentManager
from coding_kid.context import SessionContext
from coding_kid.context_manager import ContextBudget
from coding_kid.events import CancellationToken, EventSink, TurnCancelled
from coding_kid.tools import TodoState


def text_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="output_text", text=text)],
            )
        ],
        usage=None,
    )


def context(tmp_path: Path) -> SessionContext:
    return SessionContext(
        cwd=tmp_path,
        operating_system="test",
        shell="PowerShell",
        model="test/model",
        local_date="2026-08-05",
        project_root=tmp_path,
        project_instructions=(),
    )


def test_agents_run_in_parallel_and_enforce_the_running_limit(tmp_path: Path) -> None:
    barrier = threading.Barrier(2)
    release = threading.Event()

    def runner(
        manager: Any,
        todos: TodoState,
        message: str,
        token: CancellationToken,
        event_sink: EventSink,
    ) -> str:
        barrier.wait(timeout=2)
        release.wait(2)
        return f"finished {message}"

    agents = AgentManager(
        context(tmp_path),
        ContextBudget(None, "test"),
        child_runner=runner,
        max_running=2,
    )
    first = agents.start("first", "alpha")
    second = agents.start("second", "beta")

    with pytest.raises(AgentError, match="At most 2"):
        agents.start("third", "gamma")

    release.set()
    first_done, first_timed_out = agents.wait(first.agent_id, 2)
    second_done, second_timed_out = agents.wait(second.agent_id, 2)
    assert not first_timed_out and not second_timed_out
    assert first_done.status == second_done.status == "completed"
    assert first_done.result == "finished alpha"
    assert second_done.result == "finished beta"
    agents.close()


def test_followup_reuses_child_context_and_keeps_todos_isolated(tmp_path: Path) -> None:
    root_todos = TodoState([{"content": "root", "status": "pending"}])

    def runner(
        manager: Any,
        todos: TodoState,
        message: str,
        token: CancellationToken,
        event_sink: EventSink,
    ) -> str:
        todos.replace([{"content": message, "status": "completed"}])
        return ",".join(
            item["content"]
            for item in manager.conversation.active_items()
            if item.get("role") == "user"
        )

    agents = AgentManager(
        context(tmp_path), ContextBudget(None, "test"), child_runner=runner
    )
    started = agents.start("worker", "one")
    agents.wait(started.agent_id, 2)
    agents.followup(started.agent_id, "two")
    completed, timed_out = agents.wait(started.agent_id, 2)

    assert not timed_out
    assert completed.turn_count == 2
    assert completed.result == "one,two"
    assert root_todos.items == [{"content": "root", "status": "pending"}]
    agents.close()


def test_stop_reports_stopped_only_after_the_worker_exits(tmp_path: Path) -> None:
    entered = threading.Event()

    def runner(
        manager: Any,
        todos: TodoState,
        message: str,
        token: CancellationToken,
        event_sink: EventSink,
    ) -> str:
        entered.set()
        while True:
            token.raise_if_cancelled()
            time.sleep(0.005)

    agents = AgentManager(
        context(tmp_path), ContextBudget(None, "test"), child_runner=runner
    )
    started = agents.start("worker", "wait")
    assert entered.wait(1)

    stopped = agents.stop(started.agent_id, 2)

    assert stopped.status == "stopped"
    assert agents.running_count == 0
    terminal_events = [
        event for event in agents.drain_events() if event.status == "stopped"
    ]
    assert len(terminal_events) == 1
    agents.close()


def test_wait_timeout_and_cancellation_do_not_stop_the_agent(tmp_path: Path) -> None:
    release = threading.Event()

    def runner(
        manager: Any,
        todos: TodoState,
        message: str,
        token: CancellationToken,
        event_sink: EventSink,
    ) -> str:
        release.wait(2)
        return "done"

    agents = AgentManager(
        context(tmp_path), ContextBudget(None, "test"), child_runner=runner
    )
    started = agents.start("worker", "wait")
    snapshot, timed_out = agents.wait(started.agent_id, 0)
    assert timed_out and snapshot.status in {"starting", "running"}

    cancellation = CancellationToken()
    cancellation.cancel()
    with pytest.raises(TurnCancelled):
        agents.wait(started.agent_id, 1, cancellation)
    assert agents.poll(started.agent_id).status in {"starting", "running"}

    release.set()
    agents.wait(started.agent_id, 2)
    agents.close()


def test_start_failure_rolls_back_reserved_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents = AgentManager(
        context(tmp_path), ContextBudget(None, "test"), child_runner=lambda *args: "ok"
    )
    original_start = threading.Thread.start
    monkeypatch.setattr(
        threading.Thread,
        "start",
        lambda self: (_ for _ in ()).throw(RuntimeError("thread unavailable")),
    )

    with pytest.raises(RuntimeError, match="thread unavailable"):
        agents.start("worker", "task")

    monkeypatch.setattr(threading.Thread, "start", original_start)
    assert agents.list() == ()
    started = agents.start("worker", "task")
    assert agents.wait(started.agent_id, 2)[0].status == "completed"
    agents.close()


def test_retention_evicts_only_the_oldest_terminal_record(tmp_path: Path) -> None:
    release = threading.Event()

    def runner(*args: Any) -> str:
        message = args[2]
        if message == "running":
            release.wait(2)
        return message

    ids = iter(("agent_old", "agent_running", "agent_new"))
    agents = AgentManager(
        context(tmp_path),
        ContextBudget(None, "test"),
        child_runner=runner,
        id_factory=lambda: next(ids),
        max_retained=2,
    )
    old = agents.start("old", "old")
    agents.wait(old.agent_id, 2)
    running = agents.start("running", "running")
    newest = agents.start("new", "new")

    assert {item.agent_id for item in agents.list()} == {
        running.agent_id,
        newest.agent_id,
    }
    with pytest.raises(AgentError, match="Unknown or expired"):
        agents.poll(old.agent_id)
    release.set()
    agents.close()


def test_default_children_use_the_real_loop_in_parallel_with_restricted_tools(
    tmp_path: Path,
) -> None:
    barrier = threading.Barrier(2)
    calls: list[tuple[list[Any], set[str]]] = []
    calls_lock = threading.Lock()

    def provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
    ) -> SimpleNamespace:
        with calls_lock:
            calls.append((list(messages), {tool["name"] for tool in tools}))
        barrier.wait(timeout=2)
        prompt = next(
            item["content"]
            for item in messages
            if isinstance(item, dict) and item.get("role") == "user"
        )
        return text_response(f"answer for {prompt}")

    agents = AgentManager(
        context(tmp_path),
        ContextBudget(None, "test"),
        call_provider=provider,
        stream_provider=None,
    )
    first = agents.start("first", "alpha-only")
    second = agents.start("second", "beta-only")
    first_done = agents.wait(first.agent_id, 2)[0]
    second_done = agents.wait(second.agent_id, 2)[0]

    assert first_done.result == "answer for alpha-only"
    assert second_done.result == "answer for beta-only"
    assert len(calls) == 2
    for messages, names in calls:
        assert "spawn_agent" not in names
        assert "agent" not in names
        assert "task" not in names
        execute = next(tool for tool in names if tool == "execute")
        assert execute == "execute"
        user_prompts = [
            item["content"]
            for item in messages
            if isinstance(item, dict) and item.get("role") == "user"
        ]
        assert user_prompts in (["alpha-only"], ["beta-only"])
    time.sleep(0.05)
    assert len(calls) == 2
    agents.close()


def test_provider_failure_becomes_a_bounded_failed_snapshot(tmp_path: Path) -> None:
    def provider(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("provider unavailable")

    agents = AgentManager(
        context(tmp_path),
        ContextBudget(None, "test"),
        call_provider=provider,
        stream_provider=None,
    )
    started = agents.start("failure", "fail safely")
    failed, timed_out = agents.wait(started.agent_id, 2)

    assert not timed_out
    assert failed.status == "failed"
    assert failed.error == "provider unavailable"
    agents.close()


def test_ten_round_agent_stress_has_no_concurrency_or_event_leaks(
    tmp_path: Path,
) -> None:
    state_lock = threading.Lock()
    releases: dict[str, threading.Event] = {}
    entered: dict[str, threading.Event] = {}
    active = 0
    peak = 0

    def runner(
        manager: Any,
        todos: TodoState,
        message: str,
        token: CancellationToken,
        event_sink: EventSink,
    ) -> str:
        nonlocal active, peak
        round_name = message.split(":", 1)[0]
        todos.replace([{"content": message, "status": "in_progress"}])
        with state_lock:
            active += 1
            peak = max(peak, active)
            entered[message].set()
        try:
            releases[round_name].wait(2)
            token.raise_if_cancelled()
            return message
        finally:
            with state_lock:
                active -= 1

    agents = AgentManager(
        context(tmp_path), ContextBudget(None, "test"), child_runner=runner
    )
    terminal_keys: set[tuple[str, int]] = set()
    try:
        for round_index in range(10):
            round_name = f"round-{round_index}"
            releases[round_name] = threading.Event()
            messages = [f"{round_name}:{worker}" for worker in range(4)]
            for message in messages:
                entered[message] = threading.Event()
            started = [agents.start(message, message) for message in messages]
            assert all(entered[message].wait(1) for message in messages)
            releases[round_name].set()
            for snapshot in started:
                assert agents.wait(snapshot.agent_id, 2)[0].status == "completed"
            events = agents.drain_events()
            terminals = [event for event in events if event.status == "completed"]
            assert len(terminals) == 4
            for event in terminals:
                key = (event.agent_id, event.turn_count)
                assert key not in terminal_keys
                terminal_keys.add(key)
        assert peak == 4
    finally:
        agents.close()

    assert not any(
        thread.is_alive() and thread.name.startswith("coding-kid-agent_")
        for thread in threading.enumerate()
    )
