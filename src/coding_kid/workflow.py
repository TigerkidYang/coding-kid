"""Session-owned collaboration mode and approved-plan state."""

from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from enum import Enum
from threading import RLock
from typing import Any


class CollaborationMode(str, Enum):
    PLAN = "plan"
    IMPLEMENTATION = "implementation"
    REVIEW = "review"


class ApprovalPolicy(str, Enum):
    CAUTIOUS = "cautious"
    AUTO = "auto"
    FULL_ACCESS = "full-access"


@dataclass(frozen=True)
class WorkflowSnapshot:
    mode: CollaborationMode
    approved_plan: str | None
    checkpoint_id: str | None
    changes_accepted: bool


@dataclass(frozen=True)
class WorkflowModeChanged:
    previous: CollaborationMode
    current: CollaborationMode
    reason: str


class WorkflowState:
    """Mutable workflow state shared by one root session and its children."""

    def __init__(
        self,
        mode: CollaborationMode = CollaborationMode.IMPLEMENTATION,
        *,
        approved_plan: str | None = None,
        checkpoint_id: str | None = None,
        changes_accepted: bool = False,
    ) -> None:
        self._mode = mode
        self._approved_plan = approved_plan
        self._checkpoint_id = checkpoint_id
        self._changes_accepted = changes_accepted
        self._lock = RLock()
        self._events: deque[WorkflowModeChanged] = deque(maxlen=32)

    @property
    def mode(self) -> CollaborationMode:
        with self._lock:
            return self._mode

    @property
    def approved_plan(self) -> str | None:
        with self._lock:
            return self._approved_plan

    @property
    def checkpoint_id(self) -> str | None:
        with self._lock:
            return self._checkpoint_id

    @property
    def changes_accepted(self) -> bool:
        with self._lock:
            return self._changes_accepted

    def transition(self, mode: CollaborationMode, *, reason: str = "user") -> None:
        with self._lock:
            previous = self._mode
            self._mode = mode
            if previous is not mode:
                self._events.append(WorkflowModeChanged(previous, mode, reason))

    def approve_plan(self, plan: str, checkpoint_id: str) -> None:
        if not plan.strip():
            raise ValueError("approved plan must not be empty")
        with self._lock:
            previous = self._mode
            self._approved_plan = plan.strip()
            self._checkpoint_id = checkpoint_id
            self._changes_accepted = False
            self._mode = CollaborationMode.IMPLEMENTATION
            if previous is not CollaborationMode.IMPLEMENTATION:
                self._events.append(
                    WorkflowModeChanged(
                        previous,
                        CollaborationMode.IMPLEMENTATION,
                        "plan-approved",
                    )
                )

    def ensure_checkpoint(self, checkpoint_id: str) -> None:
        with self._lock:
            if self._checkpoint_id is None:
                self._checkpoint_id = checkpoint_id
                self._changes_accepted = False

    def enter_review(self) -> None:
        self.transition(CollaborationMode.REVIEW, reason="review-requested")

    def drain_events(self) -> tuple[WorkflowModeChanged, ...]:
        with self._lock:
            events = tuple(self._events)
            self._events.clear()
            return events

    def accept_changes(self) -> None:
        with self._lock:
            self._changes_accepted = True

    def clear_checkpoint(self) -> None:
        with self._lock:
            self._checkpoint_id = None

    def snapshot(self) -> WorkflowSnapshot:
        with self._lock:
            return WorkflowSnapshot(
                self._mode,
                self._approved_plan,
                self._checkpoint_id,
                self._changes_accepted,
            )

    def to_dict(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        return {
            "mode": snapshot.mode.value,
            "approved_plan": snapshot.approved_plan,
            "checkpoint_id": snapshot.checkpoint_id,
            "changes_accepted": snapshot.changes_accepted,
        }

    @classmethod
    def from_dict(cls, value: object) -> WorkflowState:
        if not isinstance(value, dict):
            return cls()
        try:
            mode = CollaborationMode(value.get("mode", "implementation"))
        except (TypeError, ValueError):
            mode = CollaborationMode.IMPLEMENTATION
        plan = value.get("approved_plan")
        checkpoint_id = value.get("checkpoint_id")
        return cls(
            mode,
            approved_plan=plan if isinstance(plan, str) else None,
            checkpoint_id=checkpoint_id if isinstance(checkpoint_id, str) else None,
            changes_accepted=value.get("changes_accepted") is True,
        )

    def instruction_text(self) -> str:
        mode = self.mode
        if mode is CollaborationMode.PLAN:
            return (
                "Workflow mode: plan. Investigate with read-only tools, ask up to "
                "three structured questions when needed, and submit the complete "
                "implementation and test plan with propose_plan. Project changes, "
                "shell commands, execution-session changes, and child Agents are "
                "unavailable; existing sessions may only be listed or inspected."
            )
        if mode is CollaborationMode.REVIEW:
            return (
                "Workflow mode: review. Inspect only the supplied stage changes and "
                "read-only project evidence. Organize the answer as issues, risks, "
                "and verification status; explicitly say when no issues were found."
            )
        plan = self.approved_plan
        suffix = f"\nApproved plan:\n{plan}" if plan else ""
        return (
            "Workflow mode: implementation. Carry out the user's approved work; "
            "side effects remain governed by approval and sandbox policy."
            f"{suffix}"
        )
