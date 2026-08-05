"""Application control plane for plan approval and stage change tracking."""

from __future__ import annotations

from dataclasses import dataclass
import json
from threading import Lock, RLock
from typing import Any, Callable

from coding_kid.checkpoints import ChangeSummary, CheckpointManager
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
        interaction_handler: InteractionHandler | None = None,
    ) -> None:
        self.state = state
        self.checkpoints = checkpoints
        self._interaction_handler = interaction_handler
        self._clear_context_requested = False
        self._lock = RLock()
        self._effect_lock = Lock()

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
        return registry.with_tool(
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
        checkpoint_id = self.checkpoints.create()
        self.state.approve_plan(plan, checkpoint_id)
        with self._lock:
            self._clear_context_requested = response.action == "approve_fresh"
        context = (
            "fresh implementation context"
            if self._clear_context_requested
            else "current context"
        )
        return (
            f"Plan approved. Checkpoint {checkpoint_id} was created; continue in "
            f"implementation mode using {context}."
        )

    def before_effect(self, effect: ToolEffect) -> None:
        if effect in {ToolEffect.READ_ONLY, ToolEffect.INTERACTION, ToolEffect.CONTROL}:
            return
        self._effect_lock.acquire()
        try:
            checkpoint_id = self.state.checkpoint_id
            if checkpoint_id is None:
                checkpoint_id = self.checkpoints.create()
                self.state.ensure_checkpoint(checkpoint_id)
            self.checkpoints.prepare_effect(checkpoint_id)
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

    def status_text(self) -> str:
        checkpoint_id = self.state.checkpoint_id
        if checkpoint_id is None:
            return "No implementation checkpoint or stage changes."
        return (
            f"Checkpoint: {checkpoint_id}\n"
            f"{self.checkpoints.changes(checkpoint_id).text()}\n\n"
            "Rollback covers tracked and non-ignored untracked project files. "
            "Ignored files, project-external effects, and remote side effects are excluded."
        )

    def review_text(self) -> str:
        checkpoint_id = self.state.checkpoint_id
        if checkpoint_id is None:
            return "No stage changes to review."
        return f"{self.status_text()}\n\n{self.checkpoints.diff_text(checkpoint_id)}"

    def rollback(self) -> ChangeSummary:
        checkpoint_id = self.state.checkpoint_id
        if checkpoint_id is None:
            raise RuntimeError("No checkpoint is available")
        changes = self.checkpoints.rollback(checkpoint_id)
        self.state.clear_checkpoint()
        self.state.transition(CollaborationMode.IMPLEMENTATION, reason="rollback")
        return changes

    def accept(self) -> ChangeSummary:
        checkpoint_id = self.state.checkpoint_id
        if checkpoint_id is None:
            raise RuntimeError("No checkpoint is available")
        changes = self.checkpoints.accept(checkpoint_id)
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
