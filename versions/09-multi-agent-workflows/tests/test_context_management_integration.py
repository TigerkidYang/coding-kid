from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from coding_kid.agent import run_turn
from coding_kid.context import SessionContext
from coding_kid.context_manager import ContextBudget, ContextManager


def text_response(text: str, input_tokens: int | None = None) -> SimpleNamespace:
    usage = (
        SimpleNamespace(input_tokens=input_tokens) if input_tokens is not None else None
    )
    return SimpleNamespace(
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="output_text", text=text)],
            )
        ],
        usage=usage,
    )


def make_manager(tmp_path: Path, budget: ContextBudget) -> ContextManager:
    context = SessionContext(
        cwd=tmp_path,
        operating_system="Windows 11",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-08-03",
        project_root=tmp_path,
        project_instructions=(),
    )
    manager = ContextManager(context, budget)
    manager.conversation.append_user("Keep requirement ALPHA")
    manager.conversation.append_model_round(
        [{"role": "assistant", "content": "old work " + "x" * 30000}]
    )
    manager.conversation.append_user("Finish using ALPHA")
    return manager


def test_run_turn_proactively_compacts_then_continues(tmp_path: Path) -> None:
    manager = make_manager(tmp_path, ContextBudget(16384, "test"))
    calls: list[tuple[bool, list[Any]]] = []
    events: list[str] = []

    def provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> SimpleNamespace:
        is_summary = "max_output_tokens" in kwargs
        calls.append((is_summary, messages))
        if is_summary:
            return text_response("Requirement ALPHA and completed old work.")
        return text_response("Finished with ALPHA.", input_tokens=1200)

    answer = run_turn(manager, provider, on_context=events.append)

    assert answer == "Finished with ALPHA."
    assert [is_summary for is_summary, _ in calls] == [True, False]
    assert len(manager.conversation.checkpoints) == 1
    assert manager.conversation.transcript[-1].kind == "model"
    assert manager.conversation.active[0].kind == "summary"
    assert any("compacting: auto" in event for event in events)


def test_run_turn_reactively_compacts_and_retries_once(tmp_path: Path) -> None:
    manager = make_manager(tmp_path, ContextBudget(None, "metadata unavailable"))
    calls: list[str] = []

    def provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> SimpleNamespace:
        if "max_output_tokens" in kwargs:
            calls.append("summary")
            return text_response("Recovered ALPHA context")
        calls.append("regular")
        if calls.count("regular") == 1:
            raise RuntimeError("maximum context length exceeded")
        return text_response("Recovered and finished.")

    answer = run_turn(manager, provider)

    assert answer == "Recovered and finished."
    assert calls == ["regular", "summary", "regular"]
    assert manager.conversation.checkpoints[0].trigger == "recovery"


def test_failed_turn_restores_state_even_after_auto_compaction(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path, ContextBudget(16384, "test"))
    snapshot = manager.clone()

    def provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> SimpleNamespace:
        if "max_output_tokens" in kwargs:
            return text_response("Temporary summary")
        raise RuntimeError("provider failed after compaction")

    with pytest.raises(RuntimeError, match="provider failed"):
        run_turn(manager, provider)

    assert manager.conversation.active_items() == snapshot.conversation.active_items()
    assert manager.conversation.checkpoints == snapshot.conversation.checkpoints


def test_three_auto_compaction_failures_disable_only_proactive_mode(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path, ContextBudget(16384, "test"))

    for _ in range(3):
        manager.record_auto_compaction_failure()

    assert manager.proactive_compaction_disabled
    assert manager.has_compactable_history()
    assert not manager.should_auto_compact("system", [])
