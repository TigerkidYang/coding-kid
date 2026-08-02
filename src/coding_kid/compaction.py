"""Summarize older active context and atomically install a checkpoint."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from coding_kid.context_manager import (
    SUMMARY_MAX_OUTPUT_TOKENS,
    ContextManager,
    ConversationSegment,
)
from coding_kid.parser import parse_output
from coding_kid.provider import is_context_window_error

SUMMARY_PROMPT = """Create a concise handoff summary for a coding agent that will continue this task.
Preserve the current user intent and corrections, constraints and project rules,
completed work, files inspected or changed, important findings and decisions,
commands and test results, errors or unresolved questions, current task state,
and the next required action. Do not call tools. Return only the summary."""

Provider = Callable[..., Any]
ContextObserver = Callable[[str], None]
MAX_SUMMARY_CONTEXT_RETRIES = 3


def _summary_input(segments: list[ConversationSegment], dropped: int) -> list[Any]:
    items = [item for segment in segments for item in segment.items]
    marker = ""
    if dropped:
        marker = (
            f"\n\nEmergency note: {dropped} oldest context segment(s) were "
            "unavailable because the summary request exceeded the model window."
        )
    return [*items, {"role": "user", "content": SUMMARY_PROMPT + marker}]


def compact_context(
    manager: ContextManager,
    call_provider: Provider,
    *,
    instructions: str,
    tools: list[dict[str, Any]],
    trigger: str,
    on_context: ContextObserver | None = None,
) -> bool:
    """Compact active history, committing only after a valid summary exists."""
    plan = manager.plan_compaction(instructions, tools)
    summary_segments = manager.summary_segments(plan)
    dropped = 0
    on_context and on_context(f"[context] compacting: {trigger}")

    while True:
        try:
            response = call_provider(
                "You summarize coding-agent context for seamless continuation.",
                _summary_input(summary_segments, dropped),
                [],
                max_output_tokens=SUMMARY_MAX_OUTPUT_TOKENS,
            )
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
    if dropped:
        on_context and on_context(
            f"[context] warning: summary omitted {dropped} oldest segment(s)"
        )
    return True
