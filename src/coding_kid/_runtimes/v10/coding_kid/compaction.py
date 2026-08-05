"""Summarize older active context and atomically install a checkpoint."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from coding_kid.context_manager import (
    SUMMARY_MAX_OUTPUT_TOKENS,
    ContextManager,
    ConversationSegment,
)
from coding_kid.events import (
    CancellationToken,
    CompactionCompleted,
    CompactionStarted,
    ContextWarning,
    EventSink,
    emit,
)
from coding_kid.parser import parse_output
from coding_kid.provider import is_context_window_error

SUMMARY_PROMPT = """Create a concise, authoritative handoff for a coding agent that will continue this task.
Use explicit sections for CURRENT INTENT, COMPLETED ACTIONS AND EVIDENCE,
CHANGES AND TESTS, and PENDING OR NEXT ACTION. Preserve user corrections,
constraints, project rules, exact evidence and values returned by tools, files
inspected or changed, decisions, commands and test results, errors, and open
questions. Distinguish completed actions from pending actions exactly: never
rewrite a completed read, edit, command, or verification as future work. The
continuing agent must be able to use recorded tool evidence without repeating
the tool call merely because the retained user request originally asked for it.
Do not call tools. Return only the handoff."""

Provider = Callable[..., Any]
ContextObserver = Callable[[str], None]
MAX_SUMMARY_CONTEXT_RETRIES = 3


def _item_value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _protocol_evidence(segments: list[ConversationSegment]) -> tuple[str, set[str]]:
    tools: set[str] = set()
    outputs = 0
    for segment in segments:
        for item in segment.items:
            item_type = _item_value(item, "type")
            if item_type == "function_call":
                name = _item_value(item, "name")
                if isinstance(name, str) and name:
                    tools.add(name)
            elif item_type == "function_call_output":
                outputs += 1
    if not tools and not outputs:
        return "", tools
    names = ", ".join(sorted(tools)) or "unknown"
    marker = (
        "\n\nSystem-verified protocol evidence: "
        f"{len(tools)} distinct function tool(s) were called ({names}); "
        f"{outputs} function result(s) are present. The handoff must not claim "
        "that no tools were called or that no tool evidence exists."
    )
    return marker, tools


def _summary_input(segments: list[ConversationSegment], dropped: int) -> list[Any]:
    items = [item for segment in segments for item in segment.items]
    marker = ""
    if dropped:
        marker = (
            f"\n\nEmergency note: {dropped} oldest context segment(s) were "
            "unavailable because the summary request exceeded the model window."
        )
    evidence, _ = _protocol_evidence(segments)
    return [
        *items,
        {"role": "user", "content": SUMMARY_PROMPT + marker + evidence},
    ]


def _validate_summary_evidence(
    summary: str, segments: list[ConversationSegment]
) -> None:
    _, tools = _protocol_evidence(segments)
    if not tools:
        return
    normalized = " ".join(summary.casefold().split())
    contradictions = (
        "no tools were called",
        "no tool calls were made",
        "no tools were used",
        "no tool-returned evidence",
        "there is no tool evidence",
        "没有调用工具",
        "未调用工具",
        "没有工具证据",
    )
    if any(phrase in normalized for phrase in contradictions):
        raise RuntimeError("Compaction summary contradicts recorded tool evidence")


def compact_context(
    manager: ContextManager,
    call_provider: Provider,
    *,
    instructions: str,
    tools: list[dict[str, Any]],
    trigger: str,
    on_context: ContextObserver | None = None,
    event_sink: EventSink | None = None,
    cancellation_token: CancellationToken | None = None,
) -> bool:
    """Compact active history, committing only after a valid summary exists."""
    plan = manager.plan_compaction(instructions, tools)
    summary_segments = manager.summary_segments(plan)
    dropped = 0
    on_context and on_context(f"[context] compacting: {trigger}")
    emit(event_sink, CompactionStarted(trigger))

    while True:
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()
        try:
            response = call_provider(
                "You summarize coding-agent context for seamless continuation.",
                _summary_input(summary_segments, dropped),
                [],
                max_output_tokens=SUMMARY_MAX_OUTPUT_TOKENS,
            )
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()
            break
        except Exception as error:
            if (
                not is_context_window_error(error)
                or dropped >= MAX_SUMMARY_CONTEXT_RETRIES
                or len(summary_segments) <= 1
            ):
                raise
            removable = next(
                (
                    index
                    for index, segment in enumerate(summary_segments)
                    if segment.kind != "user"
                ),
                None,
            )
            if removable is None:
                raise
            del summary_segments[removable]
            dropped += 1

    parsed = parse_output(response)
    if parsed.tool_calls:
        raise RuntimeError("Compaction model attempted to call a tool")
    summary = parsed.text.strip()
    if not summary:
        raise RuntimeError("Compaction model returned an empty summary")
    _validate_summary_evidence(summary, summary_segments)

    if cancellation_token is not None:
        cancellation_token.raise_if_cancelled()
    checkpoint = manager.apply_compaction(
        summary,
        plan,
        trigger=trigger,
        instructions=instructions,
        tools=tools,
        emergency_dropped_segments=dropped,
    )
    on_context and on_context(
        f"[context] compacted: {checkpoint.before_tokens} -> "
        f"{checkpoint.after_tokens} estimated tokens"
    )
    emit(
        event_sink,
        CompactionCompleted(
            trigger,
            checkpoint.before_tokens,
            checkpoint.after_tokens,
            dropped,
        ),
    )
    if dropped:
        warning = f"Summary omitted {dropped} oldest segment(s)"
        on_context and on_context(f"[context] warning: {warning.casefold()}")
        emit(event_sink, ContextWarning(warning))
    return True
