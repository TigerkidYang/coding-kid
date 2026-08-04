"""Typed lifecycle events shared by the agent loop and terminal interfaces."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event, Lock
from typing import Any, TypeAlias


class TurnCancelled(RuntimeError):
    """Raised when the current turn stops at a cooperative boundary."""

    def __init__(
        self, message: str = "Turn interrupted", *, reason: str = "interrupted"
    ):
        super().__init__(message)
        self.reason = reason


@dataclass
class CancellationToken:
    """A thread-safe cooperative cancellation signal."""

    _event: Event = field(default_factory=Event)
    _lock: Lock = field(default_factory=Lock)
    _reason: str = "interrupted"

    def cancel(self, reason: str = "interrupted") -> None:
        with self._lock:
            if self._event.is_set():
                return
            self._reason = reason
            self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            message = "Turn steered" if self.reason == "steered" else "Turn interrupted"
            raise TurnCancelled(message, reason=self.reason)

    def wait(self, timeout: float) -> bool:
        """Wait for cancellation, returning true when it arrives."""
        return self._event.wait(timeout)

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason


@dataclass(frozen=True)
class TurnStarted:
    pass


@dataclass(frozen=True)
class StepStarted:
    number: int


@dataclass(frozen=True)
class TransitionSelected:
    reason: str


@dataclass(frozen=True)
class InputQueued:
    text: str
    position: int


@dataclass(frozen=True)
class InputConsumed:
    text: str


@dataclass(frozen=True)
class InputRejected:
    message: str


@dataclass(frozen=True)
class RetryScheduled:
    category: str
    attempt: int
    delay_seconds: float


@dataclass(frozen=True)
class BudgetWarning:
    message: str


@dataclass(frozen=True)
class StallDetected:
    message: str


@dataclass(frozen=True)
class AssistantTextDelta:
    delta: str


@dataclass(frozen=True)
class AssistantStreamReset:
    reason: str


@dataclass(frozen=True)
class AssistantMessageCompleted:
    text: str
    has_tool_calls: bool


@dataclass(frozen=True)
class ToolStarted:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolCompleted:
    name: str
    arguments: dict[str, Any]
    result: str

    @property
    def failed(self) -> bool:
        return self.result.startswith("ERROR:")


@dataclass(frozen=True)
class TodoItem:
    content: str
    status: str


@dataclass(frozen=True)
class TodoUpdated:
    items: tuple[TodoItem, ...]


@dataclass(frozen=True)
class CompactionStarted:
    trigger: str


@dataclass(frozen=True)
class CompactionCompleted:
    trigger: str
    before_tokens: int
    after_tokens: int
    dropped_segments: int


@dataclass(frozen=True)
class ContextWarning:
    message: str


@dataclass(frozen=True)
class SkillLoaded:
    name: str
    source: str


@dataclass(frozen=True)
class MCPServerChanged:
    name: str
    state: str
    tool_count: int = 0


@dataclass(frozen=True)
class CapabilityWarning:
    message: str


@dataclass(frozen=True)
class TurnCompleted:
    answer: str


@dataclass(frozen=True)
class TurnInterrupted:
    message: str = "Turn interrupted"


@dataclass(frozen=True)
class TurnFailed:
    message: str


TurnEvent: TypeAlias = (
    TurnStarted
    | StepStarted
    | TransitionSelected
    | InputQueued
    | InputConsumed
    | InputRejected
    | RetryScheduled
    | BudgetWarning
    | StallDetected
    | AssistantTextDelta
    | AssistantStreamReset
    | AssistantMessageCompleted
    | ToolStarted
    | ToolCompleted
    | TodoUpdated
    | CompactionStarted
    | CompactionCompleted
    | ContextWarning
    | SkillLoaded
    | MCPServerChanged
    | CapabilityWarning
    | TurnCompleted
    | TurnInterrupted
    | TurnFailed
)
EventSink: TypeAlias = Callable[[TurnEvent], None]


def emit(sink: EventSink | None, event: TurnEvent) -> None:
    """Send an event when an observer is installed."""
    if sink is not None:
        sink(event)
