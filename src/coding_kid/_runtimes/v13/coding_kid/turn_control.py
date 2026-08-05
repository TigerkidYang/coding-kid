"""Bounded control state for one user-visible Agent turn."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock
import time

from coding_kid.events import CancellationToken


class TurnPhase(StrEnum):
    PREPARING = "preparing"
    SAMPLING = "sampling"
    EXECUTING_TOOLS = "executing_tools"
    RECOVERING = "recovering"
    VALIDATING = "validating"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class TransitionReason(StrEnum):
    TOOL_FOLLOWUP = "tool_followup"
    USER_STEER = "user_steer"
    AUTO_COMPACTION = "auto_compaction"
    PROVIDER_RETRY = "provider_retry"
    EMPTY_RESPONSE_RECOVERY = "empty_response_recovery"
    OUTPUT_LIMIT_RECOVERY = "output_limit_recovery"
    COMPLETION_RETRY = "completion_retry"
    BUDGET_EXHAUSTED = "budget_exhausted"
    STALLED = "stalled"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FATAL_ERROR = "fatal_error"


@dataclass(frozen=True)
class TurnLimits:
    max_steps: int = 80
    max_tool_calls: int = 64
    max_recoveries: int = 6
    max_identical_actions: int = 4
    max_pending_inputs: int = 8
    max_elapsed_seconds: float = 30 * 60

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class PendingInput:
    text: str
    queued_at: float


@dataclass(frozen=True)
class TurnResult:
    answer: str
    phase: TurnPhase
    reason: TransitionReason
    steps: int
    tool_calls: int
    recoveries: int
    elapsed_seconds: float
    state_changed: bool


class TurnController:
    """Own active cancellation and pending user input for one TUI turn."""

    def __init__(self, limits: TurnLimits | None = None) -> None:
        self.limits = limits or TurnLimits()
        self._lock = RLock()
        self._pending: deque[PendingInput] = deque()
        self._token: CancellationToken | None = None
        self._started_at: float | None = None

    @property
    def token(self) -> CancellationToken | None:
        with self._lock:
            return self._token

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def begin(self) -> CancellationToken:
        with self._lock:
            if self._token is not None:
                raise RuntimeError("A turn is already active")
            self._started_at = time.monotonic()
            self._token = CancellationToken()
            return self._token

    def next_step_token(self) -> CancellationToken:
        with self._lock:
            if self._token is None:
                raise RuntimeError("No turn is active")
            self._token = CancellationToken()
            return self._token

    def steer(self, text: str) -> bool:
        normalized = text.strip()
        if not normalized:
            raise ValueError("steer input must not be empty")
        with self._lock:
            if self._token is None:
                raise RuntimeError("No turn is active")
            if len(self._pending) >= self.limits.max_pending_inputs:
                return False
            self._pending.append(PendingInput(normalized, time.monotonic()))
            self._token.cancel("steered")
            return True

    def interrupt(self) -> None:
        with self._lock:
            if self._token is not None:
                self._token.cancel("interrupted")

    def take_pending(self) -> tuple[PendingInput, ...]:
        with self._lock:
            items = tuple(self._pending)
            self._pending.clear()
            return items

    def finish(self) -> None:
        with self._lock:
            self._token = None
            self._started_at = None
            self._pending.clear()
