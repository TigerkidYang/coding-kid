"""Application control plane for plan approval and stage change tracking."""

from __future__ import annotations

from dataclasses import dataclass
import json
from threading import Lock, RLock
from typing import Any, Callable

from coding_kid.checkpoints import (
    ChangeSummary,
    CheckpointManager,
    CheckpointPolicy,
    RecoveryCoverage,
)
from coding_kid.permissions import ToolEffect
from coding_kid.tools import ToolRegistry
from coding_kid.workflow import CollaborationMode, WorkflowState


@dataclass(frozen=True)
class InteractionRequest:
    kind: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class InteractionResponse:
    action: str
    values: tuple[str, ...] = ()
    feedback: str | None = None


InteractionHandler = Callable[[InteractionRequest], InteractionResponse]


class WorkflowRuntime:
    """Keep checkpoint operations outside the model-controlled tool namespace."""

    def __init__(
        self,
        state: WorkflowState,
        checkpoints: CheckpointManager,
        *,
        checkpoint_policy: CheckpointPolicy = CheckpointPolicy.REQUIRED,
        interaction_handler: InteractionHandler | None = None,
    ) -> None:
        self.state = state
        self.checkpoints = checkpoints
        self.checkpoint_policy = CheckpointPolicy(checkpoint_policy)
        self._interaction_handler = interaction_handler
        self._clear_context_requested = False
        self._lock = RLock()
        self._effect_lock = Lock()
        self._accept_listeners: list[Callable[[], object]] = []
        self._rollback_listeners: list[Callable[[], object]] = []

    def set_interaction_handler(self, handler: InteractionHandler | None) -> None:
        self._interaction_handler = handler

    def bind_registry(self, registry: ToolRegistry) -> ToolRegistry:
        registry = registry.with_tool(
            "request_user_input",
            {
                "description": (
                    "Ask the user one to three short structured questions while "
                    "planning. Each question needs two or three choices."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "questions": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 3,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "question": {"type": "string", "minLength": 1},
                                    "choices": {
                                        "type": "array",
                                        "minItems": 2,
                                        "maxItems": 3,
                                        "items": {"type": "string", "minLength": 1},
                                    },
                                },
                                "required": ["question", "choices"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["questions"],
                    "additionalProperties": False,
                },
                "function": self.request_user_input,
                "effect": ToolEffect.INTERACTION,
            },
        )
        registry = registry.with_tool(
            "propose_plan",
            {
                "description": (
                    "Submit the complete implementation, test, and real-use plan "
                    "for user approval. This is the only Plan-to-Implementation gate."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"plan": {"type": "string", "minLength": 1}},
                    "required": ["plan"],
                    "additionalProperties": False,
                },
                "function": self.propose_plan,
                "effect": ToolEffect.INTERACTION,
            },
        )
        return registry.with_tool(
            "diff",
            {
                "description": (
                    "Show the best bounded diff available for the current "
                    "implementation stage, including recovery-coverage warnings."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "function": self.diff,
                "effect": ToolEffect.READ_ONLY,
                "parallel_safe": True,
            },
        )

    def request_user_input(self, questions: list[dict[str, Any]]) -> str:
        if self.state.mode is not CollaborationMode.PLAN:
            raise RuntimeError("request_user_input is available only in plan mode")
        _validate_questions(questions)
        response = self._interact(
            InteractionRequest("questions", {"questions": questions})
        )
        if response.action == "abort":
            return "User declined to answer. Continue with best judgment."
        if len(response.values) != len(questions):
            raise RuntimeError("The interaction returned the wrong number of answers")
        return json.dumps(
            {"answers": list(response.values)}, ensure_ascii=False, sort_keys=True
        )

    def propose_plan(self, plan: str) -> str:
        if self.state.mode is not CollaborationMode.PLAN:
            raise RuntimeError("propose_plan is available only in plan mode")
        if not plan.strip():
            raise ValueError("plan must not be empty")
        response = self._interact(InteractionRequest("plan", {"plan": plan.strip()}))
        if response.action not in {"approve", "approve_fresh", "revise"}:
            raise RuntimeError("Invalid plan decision")
        if response.action == "revise":
            feedback = response.feedback or "Revise the plan and submit it again."
            return f"Plan was not approved. User feedback: {feedback}"
        checkpoint_id = self.checkpoints.create(self.checkpoint_policy)
        self.state.approve_plan(plan, checkpoint_id)
        with self._lock:
            self._clear_context_requested = response.action == "approve_fresh"
        context = (
            "fresh implementation context"
            if self._clear_context_requested
            else "current context"
        )
        status = self.checkpoints.status(checkpoint_id)
        return (
            f"Plan approved. Implementation stage {checkpoint_id} started with "
            f"{status.coverage.value} recovery coverage; continue in implementation "
            f"mode using {context}."
        )

    def before_effect(
        self,
        effect: ToolEffect,
        *,
        tool_name: str = "unknown",
        recovery_paths: tuple[str, ...] | None = None,
    ) -> str | None:
        if effect in {ToolEffect.READ_ONLY, ToolEffect.INTERACTION, ToolEffect.CONTROL}:
            return
        self._effect_lock.acquire()
        try:
            checkpoint_id = self.state.checkpoint_id
            if checkpoint_id is None:
                checkpoint_id = self.checkpoints.create(self.checkpoint_policy)
                self.state.ensure_checkpoint(checkpoint_id)
            return self.checkpoints.prepare_effect(
                checkpoint_id,
                paths=recovery_paths,
                effect_label=f"{tool_name}:{effect.value}",
            )
        except BaseException:
            self._effect_lock.release()
            raise

    def after_effect(self, effect: ToolEffect) -> ChangeSummary | None:
        if effect in {ToolEffect.READ_ONLY, ToolEffect.INTERACTION, ToolEffect.CONTROL}:
            return None
        try:
            checkpoint_id = self.state.checkpoint_id
            if checkpoint_id is None:
                raise RuntimeError("A side effect completed without a checkpoint")
            return self.checkpoints.record_effect(checkpoint_id)
        finally:
            self._effect_lock.release()

    def consume_clear_context(self) -> bool:
        with self._lock:
            requested = self._clear_context_requested
            self._clear_context_requested = False
            return requested

    def register_stage_listener(
        self,
        *,
        on_accept: Callable[[], object],
        on_rollback: Callable[[], object],
    ) -> None:
        """Attach application-owned resources to stage acceptance and rollback."""
        with self._lock:
            self._accept_listeners.append(on_accept)
            self._rollback_listeners.append(on_rollback)

    def status_text(self) -> str:
        checkpoint_id = self.state.checkpoint_id
        if checkpoint_id is None:
            return "No implementation checkpoint or stage changes."
        status = self.checkpoints.status(checkpoint_id)
        lines = [
            f"Stage: {checkpoint_id}",
            f"Checkpoint policy: {status.policy.value}",
            f"Recovery coverage: {status.coverage.value}",
            self.checkpoints.changes(checkpoint_id).text(),
        ]
        if status.degraded_reason:
            lines.append(f"Recovery note: {status.degraded_reason}")
        if status.coverage is RecoveryCoverage.SCOPED and status.uncovered_effects:
            lines.append(
                f"Uncovered effects: {len(status.uncovered_effects)}; rollback is partial."
            )
        elif status.coverage is RecoveryCoverage.FULL:
            lines.append(
                "Rollback covers tracked and non-ignored untracked project files."
            )
        elif status.coverage is RecoveryCoverage.SCOPED:
            lines.append("Rollback covers only files targeted by built-in edits.")
        else:
            if status.uncovered_effects:
                lines.append(
                    f"Uncovered effects: {len(status.uncovered_effects)}; "
                    "no application rollback is available."
                )
            lines.append("Application rollback is unavailable for this stage.")
        lines.append(
            "Ignored files, project-external effects, and remote side effects are excluded."
        )
        return "\n".join(lines)

    def review_text(self) -> str:
        checkpoint_id = self.state.checkpoint_id
        if checkpoint_id is None:
            return "No stage changes to review."
        return f"{self.status_text()}\n\n{self.checkpoints.diff_text(checkpoint_id)}"

    def diff(self) -> str:
        return self.review_text()

    def rollback(self, *, allow_partial: bool = False) -> ChangeSummary:
        checkpoint_id = self.state.checkpoint_id
        if checkpoint_id is None:
            raise RuntimeError("No checkpoint is available")
        changes = self.checkpoints.rollback(checkpoint_id, allow_partial=allow_partial)
        for listener in tuple(self._rollback_listeners):
            listener()
        self.state.clear_checkpoint()
        self.state.transition(CollaborationMode.IMPLEMENTATION, reason="rollback")
        return changes

    def accept(self) -> ChangeSummary:
        checkpoint_id = self.state.checkpoint_id
        if checkpoint_id is None:
            raise RuntimeError("No checkpoint is available")
        changes = self.checkpoints.accept(checkpoint_id)
        for listener in tuple(self._accept_listeners):
            listener()
        self.state.accept_changes()
        self.state.clear_checkpoint()
        self.state.transition(
            CollaborationMode.IMPLEMENTATION, reason="changes-accepted"
        )
        return changes

    def _interact(self, request: InteractionRequest) -> InteractionResponse:
        if self._interaction_handler is None:
            raise RuntimeError("No interactive workflow channel is available")
        return self._interaction_handler(request)


def _validate_questions(questions: list[dict[str, Any]]) -> None:
    if not 1 <= len(questions) <= 3:
        raise ValueError("questions must contain one to three items")
    for question in questions:
        if (
            not isinstance(question, dict)
            or not str(question.get("question", "")).strip()
        ):
            raise ValueError("each question needs non-empty text")
        choices = question.get("choices")
        if not isinstance(choices, list) or not 2 <= len(choices) <= 3:
            raise ValueError("each question needs two or three choices")
        if any(not isinstance(choice, str) or not choice.strip() for choice in choices):
            raise ValueError("question choices must be non-empty strings")
