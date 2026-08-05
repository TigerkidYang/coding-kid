"""Bounded process-local child Agent management."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
import secrets
import threading
import time
from typing import Any, Literal, TYPE_CHECKING

from coding_kid.context import SessionContext
from coding_kid.background_tasks import BackgroundTaskManager
from coding_kid.context_manager import ContextBudget, ContextManager
from coding_kid.events import (
    AssistantMessageCompleted,
    CancellationToken,
    CompactionStarted,
    EventSink,
    ToolCompleted,
    ToolStarted,
    TurnCancelled,
    TurnStarted,
)
from coding_kid.provider import generate, generate_streaming
from coding_kid.permissions import PermissionBroker
from coding_kid.sandbox import SandboxRuntime
from coding_kid.skills import SkillTurnState, explicit_skill_names
from coding_kid.tools import MAX_TOOL_OUTPUT_CHARS, TodoState
from coding_kid.workflow import WorkflowState
from coding_kid.workflow_runtime import WorkflowRuntime

if TYPE_CHECKING:
    from coding_kid.capabilities import CapabilityRuntime

MAX_RUNNING_AGENTS = 4
MAX_RETAINED_AGENTS = 16
MAX_AGENT_EVENTS = 64
MAX_AGENT_PROMPT_CHARS = 12_000
MAX_AGENT_DESCRIPTION_CHARS = 120
MAX_AGENT_WAIT_SECONDS = 30.0
MAX_CHILD_STEPS = 32
MAX_CHILD_TOOL_CALLS = 32
_WAIT_SLICE_SECONDS = 0.05

AgentStatus = Literal[
    "starting", "running", "stopping", "completed", "failed", "stopped"
]
Clock = Callable[[], float]
IdFactory = Callable[[], str]
ChildRunner = Callable[
    [ContextManager, TodoState, str, CancellationToken, EventSink], str
]

WORKER_INSTRUCTIONS = """
You are a child worker Agent, not the user-facing root Agent. Complete only the
delegated task. You cannot spawn other Agents. You may use continuing execution
sessions, but they are private to this Agent and are stopped when your run ends.
You share the root Agent's working directory and user permissions, so inspect
current files before editing and do not overlap writes assigned to other workers.
Use tools directly, verify proportionally, and return a concise report with
evidence. Do not ask the user questions or propose unrelated next steps.
""".strip()


class AgentError(RuntimeError):
    """Raised when an Agent lifecycle operation is invalid."""


@dataclass(frozen=True)
class AgentEvent:
    agent_id: str
    status: AgentStatus
    description: str
    turn_count: int


@dataclass(frozen=True)
class AgentSnapshot:
    agent_id: str
    status: AgentStatus
    description: str
    duration_seconds: float
    started_at: float
    ended_at: float | None
    turn_count: int
    tool_calls: int
    last_activity: str | None
    result: str | None
    error: str | None

    def model_text(self, *, wait_timed_out: bool = False) -> str:
        lines = [
            f"agent_id: {self.agent_id}",
            f"status: {self.status}",
            f"wait_timed_out: {str(wait_timed_out).lower()}",
            f"description: {self.description}",
            f"duration_seconds: {self.duration_seconds:.3f}",
            f"started_at: {self.started_at:.6f}",
            f"ended_at: {self.ended_at:.6f}"
            if self.ended_at is not None
            else "ended_at: null",
            f"turn_count: {self.turn_count}",
            f"tool_calls: {self.tool_calls}",
            f"last_activity: {self.last_activity or 'null'}",
        ]
        if self.result is not None:
            lines.extend(("result:", self.result))
        if self.error is not None:
            lines.extend(("error:", self.error))
        return "\n".join(lines)


@dataclass
class _AgentRecord:
    agent_id: str
    description: str
    manager: ContextManager
    todos: TodoState
    token: CancellationToken
    started_at: float
    status: AgentStatus = "starting"
    ended_at: float | None = None
    turn_count: int = 1
    tool_calls: int = 0
    last_activity: str | None = None
    result: str | None = None
    error: str | None = None
    generation: int = 1
    thread: threading.Thread | None = None
    condition: threading.Condition = field(
        default_factory=lambda: threading.Condition(threading.RLock())
    )


class AgentManager:
    """Own all child Agents for one root application process."""

    def __init__(
        self,
        session_context: SessionContext,
        budget: ContextBudget,
        *,
        call_provider: Callable[..., Any] = generate,
        stream_provider: Callable[..., Any] | None = generate_streaming,
        capability_runtime: CapabilityRuntime | None = None,
        child_runner: ChildRunner | None = None,
        id_factory: IdFactory | None = None,
        clock: Clock = time.monotonic,
        max_running: int = MAX_RUNNING_AGENTS,
        max_retained: int = MAX_RETAINED_AGENTS,
        sandbox_runtime: SandboxRuntime | None = None,
        permission_broker: PermissionBroker | None = None,
        workflow_state: WorkflowState | None = None,
        workflow_runtime: WorkflowRuntime | None = None,
    ) -> None:
        self.session_context = session_context
        self.budget = budget
        self.call_provider = call_provider
        self.stream_provider = stream_provider
        self.capability_runtime = capability_runtime
        self.sandbox_runtime = sandbox_runtime
        self.permission_broker = permission_broker
        self.workflow_state = workflow_state
        self.workflow_runtime = workflow_runtime
        self._child_runner = child_runner
        self._id_factory = id_factory or (lambda: f"agent_{secrets.token_hex(6)}")
        self._clock = clock
        self._max_running = max_running
        self._max_retained = max_retained
        self._agents: dict[str, _AgentRecord] = {}
        self._events: deque[AgentEvent] = deque(maxlen=MAX_AGENT_EVENTS)
        self._lock = threading.RLock()
        self._closed = False
        self._close_complete = threading.Event()

    @property
    def running_count(self) -> int:
        with self._lock:
            return sum(_is_active(item.status) for item in self._agents.values())

    def start(self, description: str, prompt: str) -> AgentSnapshot:
        description = description.strip()
        prompt = prompt.strip()
        if not description or len(description) > MAX_AGENT_DESCRIPTION_CHARS:
            raise ValueError(
                f"description must contain 1-{MAX_AGENT_DESCRIPTION_CHARS} characters"
            )
        if not prompt or len(prompt) > MAX_AGENT_PROMPT_CHARS:
            raise ValueError(
                f"prompt must contain 1-{MAX_AGENT_PROMPT_CHARS} characters"
            )
        with self._lock:
            self._require_capacity()
            self._evict_terminal_agents()
            agent_id = self._new_agent_id()
            record = _AgentRecord(
                agent_id=agent_id,
                description=description,
                manager=ContextManager(self.session_context, self.budget),
                todos=TodoState(),
                token=CancellationToken(),
                started_at=self._clock(),
            )
            self._agents[agent_id] = record
            self._events.append(AgentEvent(agent_id, "starting", description, 1))
            try:
                self._launch(record, prompt)
            except BaseException:
                del self._agents[agent_id]
                if self._events and self._events[-1].agent_id == agent_id:
                    self._events.pop()
                raise
        return self._snapshot(record)

    def list(self) -> tuple[AgentSnapshot, ...]:
        with self._lock:
            records = tuple(self._agents.values())
        return tuple(self._snapshot(record) for record in records)

    def poll(self, agent_id: str) -> AgentSnapshot:
        return self._snapshot(self._get(agent_id))

    def wait(
        self,
        agent_id: str,
        timeout_seconds: float = 10.0,
        cancellation_token: CancellationToken | None = None,
    ) -> tuple[AgentSnapshot, bool]:
        if timeout_seconds < 0 or timeout_seconds > MAX_AGENT_WAIT_SECONDS:
            raise ValueError(
                f"timeout_seconds must be between 0 and {MAX_AGENT_WAIT_SECONDS:g}"
            )
        record = self._get(agent_id)
        deadline = self._clock() + timeout_seconds
        with record.condition:
            while _is_active(record.status):
                if cancellation_token is not None:
                    cancellation_token.raise_if_cancelled()
                remaining = deadline - self._clock()
                if remaining <= 0:
                    break
                record.condition.wait(min(_WAIT_SLICE_SECONDS, remaining))
            timed_out = _is_active(record.status)
        return self._snapshot(record), timed_out

    def followup(self, agent_id: str, message: str) -> AgentSnapshot:
        message = message.strip()
        if not message or len(message) > MAX_AGENT_PROMPT_CHARS:
            raise ValueError(
                f"message must contain 1-{MAX_AGENT_PROMPT_CHARS} characters"
            )
        record = self._get(agent_id)
        with self._lock, record.condition:
            if _is_active(record.status):
                raise AgentError(f"Agent {agent_id} is already running")
            self._require_capacity()
            previous = (
                record.generation,
                record.turn_count,
                record.token,
                record.started_at,
                record.ended_at,
                record.status,
                record.result,
                record.error,
                record.thread,
            )
            record.generation += 1
            record.turn_count += 1
            record.token = CancellationToken()
            record.started_at = self._clock()
            record.ended_at = None
            record.status = "starting"
            record.result = None
            record.error = None
            self._events.append(
                AgentEvent(agent_id, "starting", record.description, record.turn_count)
            )
            try:
                self._launch(record, message)
            except BaseException:
                (
                    record.generation,
                    record.turn_count,
                    record.token,
                    record.started_at,
                    record.ended_at,
                    record.status,
                    record.result,
                    record.error,
                    record.thread,
                ) = previous
                self._events.pop()
                raise
        return self._snapshot(record)

    def stop(self, agent_id: str, timeout_seconds: float = 10.0) -> AgentSnapshot:
        record = self._get(agent_id)
        with record.condition:
            if not _is_active(record.status):
                return self._snapshot(record)
            record.status = "stopping"
            record.token.cancel()
            record.condition.notify_all()
        snapshot, _ = self.wait(agent_id, timeout_seconds)
        return snapshot

    def close(self) -> None:
        with self._lock:
            if self._closed:
                complete = self._close_complete
                owns_close = False
                records: tuple[_AgentRecord, ...] = ()
            else:
                self._closed = True
                complete = self._close_complete
                owns_close = True
                records = tuple(self._agents.values())
                for record in records:
                    with record.condition:
                        if _is_active(record.status):
                            record.status = "stopping"
                            record.token.cancel()
                            record.condition.notify_all()
        if not owns_close:
            complete.wait()
            return
        try:
            deadline = self._clock() + 10.0
            for record in records:
                thread = record.thread
                if thread is not None:
                    thread.join(max(0.0, deadline - self._clock()))
        finally:
            complete.set()

    def drain_events(self) -> tuple[AgentEvent, ...]:
        with self._lock:
            events = tuple(self._events)
            self._events.clear()
            return events

    def status_text(self) -> str:
        snapshots = self.list()
        if not snapshots:
            return "No child Agents."
        return "\n".join(
            f"{item.agent_id}  {item.status}  {_bounded(item.description)}"
            for item in snapshots
        )

    def prompt_summary(self) -> str:
        snapshots = self.list()
        running = [item for item in snapshots if _is_active(item.status)]
        terminal = [item for item in snapshots if not _is_active(item.status)][-4:]
        selected = [*running, *terminal]
        if not selected:
            return ""
        lines = [
            "Child Agents are process-local and share this working directory. "
            "Current Agents:"
        ]
        lines.extend(
            f"- {item.agent_id}: {item.status}; {_bounded(item.description)}"
            for item in selected
        )
        lines.append(
            "Use the agent tool to poll or wait for results; completion does not "
            "wake the model automatically."
        )
        return "\n".join(lines)

    def _launch(self, record: _AgentRecord, message: str) -> None:
        generation = record.generation
        thread = threading.Thread(
            target=self._run,
            args=(record, generation, message),
            daemon=True,
            name=f"coding-kid-{record.agent_id}",
        )
        record.thread = thread
        thread.start()

    def _run(self, record: _AgentRecord, generation: int, message: str) -> None:
        with record.condition:
            if record.generation != generation:
                return
            if record.token.cancelled:
                self._finish(record, generation, "stopped")
                return
            record.status = "running"
            record.condition.notify_all()
        record.manager.conversation.append_user(message)
        try:
            if self._child_runner is not None:
                result = self._child_runner(
                    record.manager,
                    record.todos,
                    message,
                    record.token,
                    lambda event: self._observe(record, event),
                )
            else:
                result = self._run_default_child(record, message)
            if record.token.cancelled:
                self._finish(record, generation, "stopped")
            else:
                self._finish(record, generation, "completed", result=result)
        except BaseException as error:
            status: AgentStatus = "stopped" if record.token.cancelled else "failed"
            detail = None if isinstance(error, TurnCancelled) else str(error)
            result = (
                _latest_tool_output(record.manager) if status == "stopped" else None
            )
            self._finish(record, generation, status, result=result, error=detail)

    def _run_default_child(self, record: _AgentRecord, message: str) -> str:
        from coding_kid.agent import run_turn
        from coding_kid.tools import build_child_tool_registry

        request_context: list[Any] = []
        overlays = [WORKER_INSTRUCTIONS]
        child_tasks = BackgroundTaskManager(sandbox_runtime=self.sandbox_runtime)
        try:
            registry = build_child_tool_registry(
                record.todos,
                record.token,
                child_tasks,
                self.sandbox_runtime,
            )
            if self.capability_runtime is not None:
                skill_state = SkillTurnState(self.capability_runtime.snapshot.skills)
                for skill_name in explicit_skill_names(
                    message, self.capability_runtime.snapshot.skills
                ):
                    request_context.append(
                        {
                            "role": "user",
                            "content": self.capability_runtime.load_skill(
                                skill_state, skill_name, explicit=True
                            ),
                        }
                    )
                registry = self.capability_runtime.registry_for_turn(
                    skill_state,
                    record.token,
                    base_registry=registry,
                )
                metadata = self.capability_runtime.skill_metadata()
                if metadata:
                    overlays.append(metadata)
            return run_turn(
                record.manager,
                self.call_provider,
                max_steps=MAX_CHILD_STEPS,
                stream_provider=self.stream_provider,
                event_sink=lambda event: self._observe(record, event),
                cancellation_token=record.token,
                request_context=request_context,
                tool_registry=registry,
                instruction_overlays=tuple(overlays),
                background_tasks=child_tasks,
                todo_state=record.todos,
                max_tool_calls=MAX_CHILD_TOOL_CALLS,
                rollback_on_cancel=False,
                permission_broker=self.permission_broker,
                workflow_state=self.workflow_state,
                workflow_runtime=self.workflow_runtime,
            )
        finally:
            child_tasks.close()
            if record.token.cancelled:
                snapshots = child_tasks.list()
                if snapshots:
                    evidence = "\n\n".join(item.model_text() for item in snapshots)
                    _replace_latest_tool_output(
                        record.manager,
                        evidence + "\nturn_interrupted: true\n"
                        "The child Agent's private execution sessions were stopped.",
                    )

    def _observe(self, record: _AgentRecord, event: Any) -> None:
        with record.condition:
            if isinstance(event, TurnStarted):
                record.last_activity = "model"
            elif isinstance(event, AssistantMessageCompleted):
                record.last_activity = "model response"
            elif isinstance(event, CompactionStarted):
                record.last_activity = "compaction"
            elif isinstance(event, ToolStarted):
                record.last_activity = event.name
            elif isinstance(event, ToolCompleted):
                record.tool_calls += 1
                record.last_activity = event.name
            record.condition.notify_all()

    def _finish(
        self,
        record: _AgentRecord,
        generation: int,
        status: AgentStatus,
        *,
        result: str | None = None,
        error: str | None = None,
    ) -> None:
        with record.condition:
            if record.generation != generation or not _is_active(record.status):
                return
            record.status = status
            record.ended_at = self._clock()
            record.result = _bounded_result(result)
            record.error = _bounded_result(error)
            record.condition.notify_all()
        with self._lock:
            self._events.append(
                AgentEvent(
                    record.agent_id, status, record.description, record.turn_count
                )
            )

    def _snapshot(self, record: _AgentRecord) -> AgentSnapshot:
        with record.condition:
            ended_at = record.ended_at or self._clock()
            return AgentSnapshot(
                agent_id=record.agent_id,
                status=record.status,
                description=record.description,
                duration_seconds=max(0.0, ended_at - record.started_at),
                started_at=record.started_at,
                ended_at=record.ended_at,
                turn_count=record.turn_count,
                tool_calls=record.tool_calls,
                last_activity=record.last_activity,
                result=record.result,
                error=record.error,
            )

    def _get(self, agent_id: str) -> _AgentRecord:
        if not agent_id:
            raise ValueError("agent_id is required")
        with self._lock:
            record = self._agents.get(agent_id)
        if record is None:
            raise AgentError(f"Unknown or expired child Agent: {agent_id}")
        return record

    def _require_capacity(self) -> None:
        if self._closed:
            raise AgentError("Agent manager is closed")
        if self.running_count >= self._max_running:
            raise AgentError(
                f"At most {self._max_running} child Agents may run at once"
            )

    def _new_agent_id(self) -> str:
        for _ in range(100):
            agent_id = self._id_factory()
            if agent_id and agent_id not in self._agents:
                return agent_id
        raise AgentError("Could not allocate a unique child Agent ID")

    def _evict_terminal_agents(self) -> None:
        while len(self._agents) >= self._max_retained:
            terminal_id = next(
                (
                    agent_id
                    for agent_id, item in self._agents.items()
                    if not _is_active(item.status)
                ),
                None,
            )
            if terminal_id is None:
                raise AgentError("Child Agent record limit reached")
            del self._agents[terminal_id]


def _is_active(status: AgentStatus) -> bool:
    return status in {"starting", "running", "stopping"}


def _bounded(value: str, limit: int = 120) -> str:
    rendered = " ".join(value.splitlines())
    return rendered if len(rendered) <= limit else f"{rendered[: limit - 3]}..."


def _bounded_result(value: str | None) -> str | None:
    if value is None or len(value) <= MAX_TOOL_OUTPUT_CHARS:
        return value
    half = MAX_TOOL_OUTPUT_CHARS // 2
    omitted = len(value) - (half * 2)
    return (
        f"{value[:half]}\n... Agent output truncated "
        f"({omitted} characters omitted) ...\n{value[-half:]}"
    )


def _latest_tool_output(manager: ContextManager) -> str | None:
    for item in reversed(manager.conversation.active_items()):
        if isinstance(item, dict) and item.get("type") == "function_call_output":
            output = item.get("output")
            return output if isinstance(output, str) else str(output)
    return None


def _replace_latest_tool_output(manager: ContextManager, output: str) -> None:
    for item in reversed(manager.conversation.active_items()):
        if isinstance(item, dict) and item.get("type") == "function_call_output":
            item["output"] = output
            return
