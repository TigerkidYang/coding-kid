"""Application-owned authorization boundary for model-requested tools."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import secrets
from threading import Condition, Lock, RLock
from typing import Any, Callable

from coding_kid.events import CancellationToken, EventSink, TurnCancelled, emit
from coding_kid.workflow import ApprovalPolicy, CollaborationMode, WorkflowState


class ToolEffect(str, Enum):
    READ_ONLY = "read-only"
    INTERACTION = "interaction"
    PROJECT_WRITE = "project-write"
    COMMAND = "command"
    DESTRUCTIVE = "destructive"
    EXTERNAL = "external"
    CONTROL = "control"


class ApprovalChoice(str, Enum):
    ONCE = "once"
    SESSION = "session"
    DENY = "deny"
    ABORT = "abort"


@dataclass(frozen=True)
class ApprovalRequest:
    request_id: str
    tool_name: str
    effect: ToolEffect
    arguments: dict[str, Any]
    summary: str
    approval_key: str


@dataclass(frozen=True)
class ApprovalResponse:
    choice: ApprovalChoice
    feedback: str | None = None


@dataclass(frozen=True)
class AuthorizationResult:
    allowed: bool
    message: str = ""


@dataclass(frozen=True)
class ApprovalRequested:
    request: ApprovalRequest


@dataclass(frozen=True)
class ApprovalResolved:
    request_id: str
    choice: ApprovalChoice
    feedback: str | None = None


@dataclass(frozen=True)
class ApprovalCancelled:
    request_id: str
    reason: str


ApprovalHandler = Callable[
    [ApprovalRequest, CancellationToken | None], ApprovalResponse
]
HardCheck = Callable[[], None]
SandboxCheck = Callable[[], None]


class PermissionBroker:
    """Enforce mode, safety, approval policy, and sandbox ordering."""

    def __init__(
        self,
        policy: ApprovalPolicy,
        workflow: WorkflowState,
        *,
        handler: ApprovalHandler | None = None,
    ) -> None:
        self.policy = policy
        self.workflow = workflow
        self._handler = handler
        self._session_grants: set[str] = set()
        self._pending: dict[str, ApprovalRequest] = {}
        self._responses: dict[str, ApprovalResponse] = {}
        self._condition = Condition(RLock())
        self._approval_lock = Lock()

    @property
    def session_grants(self) -> frozenset[str]:
        with self._condition:
            return frozenset(self._session_grants)

    @property
    def pending(self) -> tuple[ApprovalRequest, ...]:
        with self._condition:
            return tuple(self._pending.values())

    def set_handler(self, handler: ApprovalHandler | None) -> None:
        with self._condition:
            self._handler = handler

    def clear_session_grants(self) -> None:
        with self._condition:
            self._session_grants.clear()

    def resolve(self, request_id: str, response: ApprovalResponse) -> bool:
        """Resolve exactly one live request; stale and duplicate replies are ignored."""
        with self._condition:
            if request_id not in self._pending or request_id in self._responses:
                return False
            self._responses[request_id] = response
            self._condition.notify_all()
            return True

    def wait_for_response(
        self,
        request: ApprovalRequest,
        cancellation_token: CancellationToken | None,
    ) -> ApprovalResponse:
        """Thread-safe request queue used by TUI event handlers."""
        with self._condition:
            self._pending[request.request_id] = request
            try:
                while request.request_id not in self._responses:
                    if cancellation_token is not None and cancellation_token.cancelled:
                        raise TurnCancelled(
                            "Turn interrupted while waiting for approval",
                            reason=cancellation_token.reason,
                        )
                    self._condition.wait(0.05)
                return self._responses.pop(request.request_id)
            finally:
                self._pending.pop(request.request_id, None)
                self._responses.pop(request.request_id, None)

    def authorize(
        self,
        tool_name: str,
        effect: ToolEffect,
        arguments: dict[str, Any],
        *,
        hard_check: HardCheck | None = None,
        sandbox_check: SandboxCheck | None = None,
        cancellation_token: CancellationToken | None = None,
        event_sink: EventSink | None = None,
    ) -> AuthorizationResult:
        """Authorize before ToolStarted and before any actual side effect."""
        mode_error = _mode_error(self.workflow.mode, tool_name, effect)
        if mode_error:
            return AuthorizationResult(False, mode_error)
        if hard_check is not None:
            try:
                hard_check()
            except Exception as error:  # noqa: BLE001
                return AuthorizationResult(
                    False, f"Hard safety rule blocked {tool_name}: {error}"
                )

        key = approval_key(tool_name, effect, arguments)
        needs_approval = self._needs_approval(effect)
        if key not in self.session_grants and needs_approval:
            with self._approval_lock:
                if key not in self.session_grants:
                    denied = self._request_approval(
                        tool_name,
                        effect,
                        arguments,
                        key,
                        cancellation_token,
                        event_sink,
                    )
                    if denied is not None:
                        return denied

        if sandbox_check is not None:
            try:
                sandbox_check()
            except Exception as error:  # noqa: BLE001
                return AuthorizationResult(
                    False, f"Sandbox blocked {tool_name}: {error}"
                )
        return AuthorizationResult(True)

    def _request_approval(
        self,
        tool_name: str,
        effect: ToolEffect,
        arguments: dict[str, Any],
        key: str,
        cancellation_token: CancellationToken | None,
        event_sink: EventSink | None,
    ) -> AuthorizationResult | None:
        request = ApprovalRequest(
            f"approval_{secrets.token_hex(6)}",
            tool_name,
            effect,
            dict(arguments),
            approval_summary(tool_name, effect, arguments),
            key,
        )
        emit(event_sink, ApprovalRequested(request))
        handler = self._handler
        if handler is None:
            response = ApprovalResponse(
                ApprovalChoice.DENY,
                "No interactive approval channel is available.",
            )
        else:
            try:
                response = handler(request, cancellation_token)
            except TurnCancelled as error:
                emit(event_sink, ApprovalCancelled(request.request_id, str(error)))
                raise
        emit(
            event_sink,
            ApprovalResolved(request.request_id, response.choice, response.feedback),
        )
        if response.choice is ApprovalChoice.ABORT:
            raise TurnCancelled("Turn aborted from approval prompt")
        if response.choice is ApprovalChoice.DENY:
            feedback = f" Feedback: {response.feedback}" if response.feedback else ""
            return AuthorizationResult(False, f"User denied {tool_name}.{feedback}")
        if response.choice is ApprovalChoice.SESSION:
            with self._condition:
                self._session_grants.add(key)
        return None

    def _needs_approval(self, effect: ToolEffect) -> bool:
        if effect in {ToolEffect.READ_ONLY, ToolEffect.INTERACTION, ToolEffect.CONTROL}:
            return False
        if self.policy is ApprovalPolicy.FULL_ACCESS:
            return False
        if self.policy is ApprovalPolicy.AUTO:
            return effect is not ToolEffect.PROJECT_WRITE
        return True


def _mode_error(
    mode: CollaborationMode, tool_name: str, effect: ToolEffect
) -> str | None:
    if mode is CollaborationMode.IMPLEMENTATION:
        return None
    allowed_names = (
        {"read", "search", "skill", "request_user_input", "propose_plan"}
        if mode is CollaborationMode.PLAN
        else {"read", "search", "skill"}
    )
    if tool_name in allowed_names or (
        tool_name == "task" and effect is ToolEffect.READ_ONLY
    ):
        return None
    return f"Workflow mode {mode.value} blocks tool {tool_name} ({effect.value})"


def approval_key(tool_name: str, effect: ToolEffect, arguments: dict[str, Any]) -> str:
    if effect in {ToolEffect.PROJECT_WRITE, ToolEffect.DESTRUCTIVE}:
        target = str(arguments.get("path", "")).strip()
        try:
            target = str(Path(target).resolve(strict=False))
        except OSError:
            pass
        return f"{tool_name}:path:{target.casefold()}"
    if effect is ToolEffect.COMMAND:
        if tool_name == "task":
            action = str(arguments.get("action", ""))
            task_id = str(arguments.get("task_id", ""))
            payload = (
                arguments.get("input", "")
                if action == "write"
                else arguments.get("command", "")
            )
            normalized = " ".join(str(payload).split())
            return f"task:{action}:{task_id}:{normalized}"
        command = " ".join(str(arguments.get("command", "")).split())
        background = bool(arguments.get("background", False))
        interactive = bool(arguments.get("interactive", False))
        return f"{tool_name}:command:{background}:{interactive}:{command}"
    if effect is ToolEffect.EXTERNAL:
        server = str(arguments.get("_server", "dynamic"))
        return f"external:{server}:{tool_name}"
    if tool_name in {"spawn_agent", "agent"}:
        action = arguments.get("action", "spawn")
        return f"agent:{action}"
    return f"{effect.value}:{tool_name}"


def approval_summary(
    tool_name: str, effect: ToolEffect, arguments: dict[str, Any]
) -> str:
    if effect is ToolEffect.COMMAND:
        if tool_name == "task":
            action = arguments.get("action", "")
            payload = (
                arguments.get("input", "")
                if action == "write"
                else arguments.get("command", "")
            )
            return (
                f"Execution session: {arguments.get('task_id', '')}\n"
                f"Action: {action}\n"
                f"Payload: {payload}\n"
                f"Reason: {arguments.get('reason') or 'not provided'}"
            )
        return (
            f"Command: {arguments.get('command', '')}\n"
            f"Working directory: {Path.cwd()}\n"
            f"Background: {bool(arguments.get('background', False))}\n"
            f"Interactive: {bool(arguments.get('interactive', False))}\n"
            f"Reason: {arguments.get('reason') or 'not provided'}"
        )
    if effect in {ToolEffect.PROJECT_WRITE, ToolEffect.DESTRUCTIVE}:
        lines = [f"Target: {arguments.get('path', '')}"]
        if tool_name == "write":
            lines.append(
                f"New content preview:\n{str(arguments.get('content', ''))[:2_000]}"
            )
        elif tool_name == "patch":
            lines.append(f"Replace:\n{str(arguments.get('old_text', ''))[:1_000]}")
            lines.append(f"With:\n{str(arguments.get('new_text', ''))[:1_000]}")
        return "\n".join(lines)
    bounded = json.dumps(arguments, ensure_ascii=False, default=str)
    if len(bounded) > 2_000:
        bounded = f"{bounded[:2_000]}…"
    return f"{tool_name} ({effect.value}): {bounded}"
