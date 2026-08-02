from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from coding_kid.compaction import compact_context
from coding_kid.context import SessionContext
from coding_kid.context_manager import ContextBudget, ContextManager


def text_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="output_text", text=text)],
            )
        ]
    )


def make_manager(tmp_path: Path) -> ContextManager:
    context = SessionContext(
        cwd=tmp_path,
        operating_system="Windows 11",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-08-03",
        project_root=tmp_path,
        project_instructions=(),
    )
    manager = ContextManager(context, ContextBudget(32768, "test"))
    manager.conversation.append_user("Remember requirement ALPHA")
    manager.conversation.append_model_round(
        [{"role": "assistant", "content": "old evidence " + "x" * 30000}]
    )
    manager.conversation.append_user("Continue and keep ALPHA")
    return manager


def test_compaction_atomically_replaces_only_active_context(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    transcript_before = manager.conversation.transcript.copy()
    events: list[str] = []
    calls: list[tuple[list[Any], list[dict[str, Any]], int | None]] = []

    def provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
        *,
        max_output_tokens: int | None = None,
    ) -> SimpleNamespace:
        calls.append((messages, tools, max_output_tokens))
        return text_response("Intent ALPHA; continue the current task.")

    assert compact_context(
        manager,
        provider,
        instructions="system",
        tools=[{"type": "function", "name": "read"}],
        trigger="manual",
        on_context=events.append,
    )

    assert manager.conversation.transcript == transcript_before
    assert len(manager.conversation.checkpoints) == 1
    assert manager.conversation.active[0].kind == "summary"
    assert "Intent ALPHA" in manager.conversation.active[0].items[0]["content"]
    assert manager.conversation.active[-1].items == [
        {"role": "user", "content": "Continue and keep ALPHA"}
    ]
    assert calls[0][1] == []
    assert calls[0][2] == 4096
    summary_request = calls[0][0][-1]["content"]
    assert "COMPLETED ACTIONS AND EVIDENCE" in summary_request
    assert "retained user request originally asked for it" in summary_request
    checkpoint = manager.conversation.active[0].items[0]["content"]
    assert "Treat the checkpoint as authoritative history" in checkpoint
    assert "do not repeat them merely" in checkpoint
    assert events[0] == "[context] compacting: manual"
    assert events[-1].startswith("[context] compacted:")


def test_empty_summary_does_not_change_state(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    snapshot = manager.clone()

    with pytest.raises(RuntimeError, match="empty summary"):
        compact_context(
            manager,
            lambda *args, **kwargs: text_response("   "),
            instructions="system",
            tools=[],
            trigger="auto",
        )

    assert manager.conversation.active_items() == snapshot.conversation.active_items()
    assert manager.conversation.checkpoints == []


def test_summary_context_error_drops_oldest_non_user_segment_and_retries(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)
    calls = 0
    events: list[str] = []

    def provider(*args: Any, **kwargs: Any) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("maximum context length exceeded")
        return text_response("Recovered handoff")

    compact_context(
        manager,
        provider,
        instructions="system",
        tools=[],
        trigger="recovery",
        on_context=events.append,
    )

    assert calls == 2
    assert manager.conversation.checkpoints[0].emergency_dropped_segments == 1
    assert any("omitted 1 oldest" in event for event in events)
