from pathlib import Path
from types import SimpleNamespace

import pytest

import coding_kid.context_manager as context_manager_module
from coding_kid.context import SessionContext
from coding_kid.context_manager import (
    ContextBudget,
    ContextManager,
    ConversationState,
    estimate_request_tokens,
)


def make_session_context(tmp_path: Path, model: str = "test/model") -> SessionContext:
    return SessionContext(
        cwd=tmp_path,
        operating_system="Windows 11",
        shell="cmd.exe",
        model=model,
        local_date="2026-08-03",
        project_root=tmp_path,
        project_instructions=(),
    )


def test_context_budget_prefers_valid_environment_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODING_KID_CONTEXT_WINDOW", "32768")
    monkeypatch.setattr(
        context_manager_module,
        "discover_context_length",
        lambda model: pytest.fail("metadata should not be requested"),
    )

    budget = ContextBudget.capture("test/model")

    assert budget == ContextBudget(32768, "environment override")
    assert budget.auto_compact_threshold == 24576


@pytest.mark.parametrize("value", ["nope", "16383"])
def test_context_budget_rejects_invalid_override(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("CODING_KID_CONTEXT_WINDOW", value)

    with pytest.raises(RuntimeError, match="CODING_KID_CONTEXT_WINDOW"):
        ContextBudget.capture("test/model")


def test_context_budget_uses_metadata_or_degrades_to_passive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CODING_KID_CONTEXT_WINDOW", raising=False)
    monkeypatch.setattr(
        context_manager_module,
        "discover_context_length",
        lambda model: 128000 if model == "known/model" else None,
    )

    assert ContextBudget.capture("known/model") == ContextBudget(
        128000,
        "OpenRouter metadata",
    )
    assert ContextBudget.capture("missing/model") == ContextBudget(
        None,
        "OpenRouter metadata unavailable",
    )


def test_conversation_keeps_canonical_transcript_separate_from_active() -> None:
    state = ConversationState()
    state.append_user("Fix it")
    state.append_model_round(
        [
            SimpleNamespace(type="function_call", call_id="1"),
            {"type": "function_call_output", "call_id": "1", "output": "ok"},
        ]
    )

    state.active[1].items[1] = {"changed": True}

    assert state.transcript[1].items[1]["output"] == "ok"
    assert state.active_items()[0] == {"role": "user", "content": "Fix it"}
    assert len(state.transcript) == len(state.active) == 2


def test_request_estimate_counts_utf8_and_protocol_items(tmp_path: Path) -> None:
    context = make_session_context(tmp_path)
    manager = ContextManager(context, ContextBudget(None, "test"))
    manager.conversation.append_user("中文 context")

    estimate = manager.request_estimate(
        "system",
        [{"type": "function", "name": "read"}],
    )

    assert estimate == estimate_request_tokens(
        "system",
        manager.model_input(),
        [{"type": "function", "name": "read"}],
    )
    assert estimate > 32


def test_provider_usage_calibrates_future_estimates(tmp_path: Path) -> None:
    manager = ContextManager(
        make_session_context(tmp_path),
        ContextBudget(128000, "test"),
    )

    manager.record_regular_response(
        SimpleNamespace(usage=SimpleNamespace(input_tokens=300)),
        local_estimate=100,
    )

    assert manager.last_actual_input_tokens == 300
    assert manager.calibration_factor == 3.0


def test_compaction_plan_preserves_latest_user_and_complete_model_rounds(
    tmp_path: Path,
) -> None:
    manager = ContextManager(
        make_session_context(tmp_path),
        ContextBudget(32768, "test"),
    )
    manager.conversation.append_user("Old request")
    manager.conversation.append_model_round(
        [{"role": "assistant", "content": "x" * 9000}]
    )
    manager.conversation.append_user("Latest correction")
    manager.conversation.append_model_round(
        [
            {"type": "function_call", "call_id": "recent"},
            {
                "type": "function_call_output",
                "call_id": "recent",
                "output": "recent evidence",
            },
        ]
    )

    plan = manager.plan_compaction("system", [])

    assert plan.latest_user_index == 2
    assert 2 in plan.retained_indices
    assert 0 in plan.compactable_indices
    for index in plan.retained_indices:
        segment = manager.conversation.active[index]
        if segment.kind == "model" and len(segment.items) == 2:
            assert segment.items[0]["call_id"] == segment.items[1]["call_id"]


def test_manager_snapshot_restores_active_transcript_and_accounting(
    tmp_path: Path,
) -> None:
    manager = ContextManager(
        make_session_context(tmp_path),
        ContextBudget(32768, "test"),
    )
    manager.conversation.append_user("before")
    snapshot = manager.clone()

    manager.conversation.append_model_round([{"content": "temporary"}])
    manager.calibration_factor = 2.0
    manager.record_auto_compaction_failure()
    manager.restore(snapshot)

    assert manager.conversation.active_items() == [
        {"role": "user", "content": "before"}
    ]
    assert manager.calibration_factor == 1.0
    assert manager.consecutive_auto_compaction_failures == 0


def test_context_status_reports_passive_mode(tmp_path: Path) -> None:
    manager = ContextManager(
        make_session_context(tmp_path),
        ContextBudget(None, "metadata unavailable"),
    )
    manager.conversation.append_user("hello")

    rendered = manager.status_text("system", [])

    assert "Context mode: passive" in rendered
    assert "Context window: unknown" in rendered
    assert "Compactions: 0" in rendered
