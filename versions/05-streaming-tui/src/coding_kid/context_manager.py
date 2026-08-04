"""Manage bounded, model-visible conversation context for one chat."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Literal

from coding_kid.context import SessionContext, build_model_input
from coding_kid.provider import discover_context_length, response_input_tokens

MIN_CONTEXT_WINDOW = 16_384
SUMMARY_MAX_OUTPUT_TOKENS = 4_096
SUMMARY_RESERVE_TOKENS = 8_192
PROTOCOL_ITEM_OVERHEAD_TOKENS = 16
MAX_CONSECUTIVE_AUTO_COMPACTION_FAILURES = 3

SegmentKind = Literal["user", "model", "summary"]


def _json_default(value: Any) -> Any:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    if hasattr(value, "__dict__"):
        return vars(value)
    return str(value)


def estimate_tokens(value: Any, *, item_count: int = 1) -> int:
    """Conservatively estimate tokens for provider-shaped values."""
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=_json_default,
    )
    byte_count = len(rendered.encode("utf-8"))
    return math.ceil(byte_count / 3) + PROTOCOL_ITEM_OVERHEAD_TOKENS * item_count


def estimate_request_tokens(
    instructions: str,
    model_input: list[Any],
    tools: list[dict[str, Any]],
) -> int:
    """Estimate one complete request, including tool schemas and overhead."""
    return estimate_tokens(
        {
            "instructions": instructions,
            "input": model_input,
            "tools": tools,
        },
        item_count=1 + len(model_input) + len(tools),
    )


@dataclass
class ConversationSegment:
    """One protocol-safe unit in the conversation."""

    kind: SegmentKind
    items: list[Any]

    def clone(self) -> ConversationSegment:
        return ConversationSegment(self.kind, list(self.items))


@dataclass(frozen=True)
class CompactionCheckpoint:
    """A record that active context was replaced without erasing transcript."""

    summary: str
    trigger: str
    before_tokens: int
    after_tokens: int
    emergency_dropped_segments: int = 0


@dataclass
class ConversationState:
    """Complete real transcript plus the bounded view sent to the model."""

    transcript: list[ConversationSegment] = field(default_factory=list)
    active: list[ConversationSegment] = field(default_factory=list)
    checkpoints: list[CompactionCheckpoint] = field(default_factory=list)

    @classmethod
    def from_items(cls, items: list[Any]) -> ConversationState:
        """Build a compatibility state from the Version 03 flat history."""
        state = cls()
        current_model: ConversationSegment | None = None
        for item in items:
            if isinstance(item, dict) and item.get("role") == "user":
                segment = ConversationSegment("user", [item])
                state.transcript.append(segment.clone())
                state.active.append(segment)
                current_model = None
            else:
                if current_model is None:
                    current_model = ConversationSegment("model", [])
                    state.transcript.append(current_model.clone())
                    state.active.append(current_model)
                current_model.items.append(item)
                state.transcript[-1].items.append(item)
        return state

    def append_user(self, content: str) -> None:
        item = {"role": "user", "content": content}
        segment = ConversationSegment("user", [item])
        self.transcript.append(segment.clone())
        self.active.append(segment)

    def append_model_round(self, items: list[Any]) -> None:
        segment = ConversationSegment("model", list(items))
        self.transcript.append(segment.clone())
        self.active.append(segment)

    def active_items(self) -> list[Any]:
        return [item for segment in self.active for item in segment.items]

    def clone(self) -> ConversationState:
        return ConversationState(
            transcript=[segment.clone() for segment in self.transcript],
            active=[segment.clone() for segment in self.active],
            checkpoints=list(self.checkpoints),
        )

    def restore(self, snapshot: ConversationState) -> None:
        self.transcript = [segment.clone() for segment in snapshot.transcript]
        self.active = [segment.clone() for segment in snapshot.active]
        self.checkpoints = list(snapshot.checkpoints)


@dataclass(frozen=True)
class ContextBudget:
    """One session's model-window knowledge and proactive threshold."""

    context_length: int | None
    source: str

    @property
    def proactive_enabled(self) -> bool:
        return self.context_length is not None

    @property
    def auto_compact_threshold(self) -> int | None:
        if self.context_length is None:
            return None
        return min(
            math.floor(self.context_length * 0.9),
            self.context_length - SUMMARY_RESERVE_TOKENS,
        )

    @classmethod
    def capture(cls, model: str) -> ContextBudget:
        override = os.getenv("CODING_KID_CONTEXT_WINDOW")
        if override is not None:
            try:
                context_length = int(override)
            except ValueError as error:
                raise RuntimeError(
                    "CODING_KID_CONTEXT_WINDOW must be an integer"
                ) from error
            if context_length < MIN_CONTEXT_WINDOW:
                raise RuntimeError(
                    f"CODING_KID_CONTEXT_WINDOW must be at least {MIN_CONTEXT_WINDOW}"
                )
            return cls(context_length, "environment override")

        if not model or model == "not set":
            return cls(None, "model metadata unavailable")
        context_length = discover_context_length(model)
        if context_length is None or context_length < MIN_CONTEXT_WINDOW:
            return cls(None, "OpenRouter metadata unavailable")
        return cls(context_length, "OpenRouter metadata")


@dataclass(frozen=True)
class CompactionPlan:
    """The active segments to summarize and retain."""

    compactable_indices: tuple[int, ...]
    retained_indices: tuple[int, ...]
    latest_user_index: int
    before_tokens: int


@dataclass
class ContextManager:
    """Own request projection, accounting, and active-context transitions."""

    session_context: SessionContext
    budget: ContextBudget
    conversation: ConversationState = field(default_factory=ConversationState)
    calibration_factor: float = 1.0
    last_actual_input_tokens: int | None = None
    last_estimated_input_tokens: int | None = None
    consecutive_auto_compaction_failures: int = 0
    proactive_compaction_disabled: bool = False

    @classmethod
    def capture(cls, session_context: SessionContext) -> ContextManager:
        return cls(session_context, ContextBudget.capture(session_context.model))

    def clone(self) -> ContextManager:
        return ContextManager(
            session_context=self.session_context,
            budget=self.budget,
            conversation=self.conversation.clone(),
            calibration_factor=self.calibration_factor,
            last_actual_input_tokens=self.last_actual_input_tokens,
            last_estimated_input_tokens=self.last_estimated_input_tokens,
            consecutive_auto_compaction_failures=(
                self.consecutive_auto_compaction_failures
            ),
            proactive_compaction_disabled=self.proactive_compaction_disabled,
        )

    def restore(self, snapshot: ContextManager) -> None:
        self.conversation.restore(snapshot.conversation)
        self.calibration_factor = snapshot.calibration_factor
        self.last_actual_input_tokens = snapshot.last_actual_input_tokens
        self.last_estimated_input_tokens = snapshot.last_estimated_input_tokens
        self.consecutive_auto_compaction_failures = (
            snapshot.consecutive_auto_compaction_failures
        )
        self.proactive_compaction_disabled = snapshot.proactive_compaction_disabled

    def model_input(self) -> list[Any]:
        return build_model_input(
            self.session_context,
            self.conversation.active_items(),
        )

    def request_estimate(
        self,
        instructions: str,
        tools: list[dict[str, Any]],
        *,
        segments: list[ConversationSegment] | None = None,
    ) -> int:
        items = (
            self.conversation.active_items()
            if segments is None
            else [item for segment in segments for item in segment.items]
        )
        model_input = build_model_input(self.session_context, items)
        local_estimate = estimate_request_tokens(instructions, model_input, tools)
        return math.ceil(local_estimate * self.calibration_factor)

    def record_regular_response(self, response: Any, local_estimate: int) -> None:
        self.last_estimated_input_tokens = local_estimate
        actual = response_input_tokens(response)
        if actual is None:
            return
        self.last_actual_input_tokens = actual
        if local_estimate > 0:
            self.calibration_factor = max(1.0, actual / local_estimate)

    def should_auto_compact(
        self,
        instructions: str,
        tools: list[dict[str, Any]],
    ) -> bool:
        threshold = self.budget.auto_compact_threshold
        return (
            threshold is not None
            and not self.proactive_compaction_disabled
            and self.request_estimate(instructions, tools) >= threshold
            and self.has_compactable_history()
        )

    def has_compactable_history(self) -> bool:
        if not self.conversation.active:
            return False
        latest_user = self._latest_user_index()
        return any(
            index != latest_user
            for index, segment in enumerate(self.conversation.active)
            if segment.kind in {"user", "model", "summary"}
        )

    def _latest_user_index(self) -> int:
        for index in range(len(self.conversation.active) - 1, -1, -1):
            if self.conversation.active[index].kind == "user":
                return index
        raise RuntimeError("No real user message is available to preserve")

    def plan_compaction(
        self,
        instructions: str,
        tools: list[dict[str, Any]],
    ) -> CompactionPlan:
        active = self.conversation.active
        latest_user = self._latest_user_index()
        before_tokens = self.request_estimate(instructions, tools)
        threshold = self.budget.auto_compact_threshold
        target = (
            max(SUMMARY_RESERVE_TOKENS, threshold // 2)
            if threshold is not None
            else max(SUMMARY_RESERVE_TOKENS, before_tokens // 2)
        )

        summary_placeholder = ConversationSegment(
            "summary",
            [
                {
                    "role": "user",
                    "content": "S" * (SUMMARY_MAX_OUTPUT_TOKENS * 3),
                }
            ],
        )
        retained = {latest_user}
        for index in range(len(active) - 1, -1, -1):
            if index == latest_user or active[index].kind != "model":
                continue
            candidate_indices = sorted({*retained, index})
            candidate_segments = [summary_placeholder] + [
                active[candidate] for candidate in candidate_indices
            ]
            if (
                self.request_estimate(
                    instructions,
                    tools,
                    segments=candidate_segments,
                )
                <= target
            ):
                retained.add(index)

        compactable = tuple(
            index for index in range(len(active)) if index not in retained
        )
        if not compactable:
            raise RuntimeError("Not enough conversation history to compact")
        return CompactionPlan(
            compactable_indices=compactable,
            retained_indices=tuple(sorted(retained)),
            latest_user_index=latest_user,
            before_tokens=before_tokens,
        )

    def summary_segments(self, plan: CompactionPlan) -> list[ConversationSegment]:
        included = {*plan.compactable_indices, plan.latest_user_index}
        return [self.conversation.active[index].clone() for index in sorted(included)]

    def apply_compaction(
        self,
        summary: str,
        plan: CompactionPlan,
        *,
        trigger: str,
        instructions: str,
        tools: list[dict[str, Any]],
        emergency_dropped_segments: int = 0,
    ) -> CompactionCheckpoint:
        summary_segment = ConversationSegment(
            "summary",
            [
                {
                    "role": "user",
                    "content": (
                        "This conversation continues from a bounded context "
                        "checkpoint. Treat the checkpoint as authoritative "
                        "history. Actions and evidence recorded as completed "
                        "are already available: do not repeat them merely "
                        "because the retained user request below originally "
                        "asked for them. Repeat an action only when the "
                        "checkpoint marks it missing, stale, failed, or still "
                        f"pending.\n\n{summary.strip()}"
                    ),
                }
            ],
        )
        retained = [
            self.conversation.active[index].clone() for index in plan.retained_indices
        ]
        previous_active = self.conversation.active
        self.conversation.active = [summary_segment, *retained]
        after_tokens = self.request_estimate(instructions, tools)
        if (
            self.budget.auto_compact_threshold is not None
            and after_tokens >= self.budget.auto_compact_threshold
        ):
            self.conversation.active = previous_active
            raise RuntimeError("Compacted context still exceeds the safe threshold")
        checkpoint = CompactionCheckpoint(
            summary=summary.strip(),
            trigger=trigger,
            before_tokens=plan.before_tokens,
            after_tokens=after_tokens,
            emergency_dropped_segments=emergency_dropped_segments,
        )
        self.conversation.checkpoints.append(checkpoint)
        self.consecutive_auto_compaction_failures = 0
        self.proactive_compaction_disabled = False
        return checkpoint

    def record_auto_compaction_failure(self) -> None:
        self.consecutive_auto_compaction_failures += 1
        if (
            self.consecutive_auto_compaction_failures
            >= MAX_CONSECUTIVE_AUTO_COMPACTION_FAILURES
        ):
            self.proactive_compaction_disabled = True

    def status_text(
        self,
        instructions: str,
        tools: list[dict[str, Any]],
    ) -> str:
        estimate = self.request_estimate(instructions, tools)
        threshold = self.budget.auto_compact_threshold
        mode = (
            "passive"
            if not self.budget.proactive_enabled or self.proactive_compaction_disabled
            else "proactive"
        )
        remaining = (
            "unknown" if threshold is None else str(max(0, threshold - estimate))
        )
        return "\n".join(
            [
                f"Context model: {self.session_context.model}",
                f"Context mode: {mode} ({self.budget.source})",
                f"Context window: {self.budget.context_length or 'unknown'}",
                f"Auto-compact threshold: {threshold or 'unknown'}",
                f"Current request estimate: {estimate}",
                f"Last provider input tokens: {self.last_actual_input_tokens or 'unknown'}",
                f"Tokens until compaction: {remaining}",
                f"Compactions: {len(self.conversation.checkpoints)}",
            ]
        )

    def context_remaining_percent(self) -> int | None:
        """Return a small footer-friendly view of remaining model context."""
        if self.budget.context_length is None:
            return None
        used = self.last_actual_input_tokens
        if used is None:
            used = self.last_estimated_input_tokens
        if used is None:
            return 100
        remaining = 100 - round(used * 100 / self.budget.context_length)
        return max(0, min(100, remaining))
