"""Typed lifecycle events shared by the agent loop and terminal interfaces."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event
from typing import Any, TypeAlias


class TurnCancelled(RuntimeError):
    """Raised when the current turn stops at a cooperative boundary."""


@dataclass
class CancellationToken:
    """A thread-safe cooperative cancellation signal."""

    _event: Event = field(default_factory=Event)

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise TurnCancelled("Turn interrupted")


@dataclass(frozen=True)
class TurnStarted:
    pass


@dataclass(frozen=True)
class AssistantTextDelta:
    delta: str


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
    | AssistantTextDelta
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
