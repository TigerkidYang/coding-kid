from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import threading

import pytest

from coding_kid.events import CancellationToken, TurnCancelled
from coding_kid.permissions import (
    ApprovalChoice,
    ApprovalRequest,
    ApprovalResponse,
    PermissionBroker,
    ToolEffect,
    approval_key,
)
from coding_kid.sandbox import SandboxConfig, SandboxMode, SandboxRuntime
from coding_kid.tools import ToolRegistry, build_tool_registry
from coding_kid.workflow import ApprovalPolicy, CollaborationMode, WorkflowState


@pytest.mark.parametrize("mode", list(CollaborationMode))
@pytest.mark.parametrize("policy", list(ApprovalPolicy))
@pytest.mark.parametrize("sandbox", list(SandboxMode))
def test_read_is_available_across_three_independent_axes(
    tmp_path: Path,
    mode: CollaborationMode,
    policy: ApprovalPolicy,
    sandbox: SandboxMode,
) -> None:
    workflow = WorkflowState(mode)
    broker = PermissionBroker(policy, workflow)

    result = broker.authorize("read", ToolEffect.READ_ONLY, {"path": "a.txt"})

    assert result.allowed


@pytest.mark.parametrize("mode", [CollaborationMode.PLAN, CollaborationMode.REVIEW])
def test_non_implementation_modes_structurally_hide_mutating_tools(
    mode: CollaborationMode,
) -> None:
    names = {item["name"] for item in ToolRegistry().definitions_for_mode(mode)}

    assert {"read", "search"} <= names
    assert not names.intersection(
        {"write", "patch", "delete", "execute", "spawn_agent", "agent", "task"}
    )


def test_mode_denial_happens_without_approval_prompt() -> None:
    called = False

    def handler(*_args: object) -> ApprovalResponse:
        nonlocal called
        called = True
        return ApprovalResponse(ApprovalChoice.ONCE)

    broker = PermissionBroker(
        ApprovalPolicy.CAUTIOUS,
        WorkflowState(CollaborationMode.PLAN),
        handler=handler,
    )

    result = broker.authorize("write", ToolEffect.PROJECT_WRITE, {"path": "x"})

    assert not result.allowed
    assert "plan" in result.message
    assert not called


def test_hard_rule_precedes_cached_session_grant() -> None:
    responses = iter([ApprovalResponse(ApprovalChoice.SESSION)])
    broker = PermissionBroker(
        ApprovalPolicy.CAUTIOUS,
        WorkflowState(),
        handler=lambda *_: next(responses),
    )
    args = {"path": "x"}
    assert broker.authorize("write", ToolEffect.PROJECT_WRITE, args).allowed

    result = broker.authorize(
        "write",
        ToolEffect.PROJECT_WRITE,
        args,
        hard_check=lambda: (_ for _ in ()).throw(PermissionError("protected")),
    )

    assert not result.allowed
    assert "Hard safety" in result.message


def test_auto_only_skips_ordinary_project_write() -> None:
    prompts: list[ApprovalRequest] = []

    def handler(request: ApprovalRequest, *_: object) -> ApprovalResponse:
        prompts.append(request)
        return ApprovalResponse(ApprovalChoice.ONCE)

    broker = PermissionBroker(ApprovalPolicy.AUTO, WorkflowState(), handler=handler)

    assert broker.authorize("write", ToolEffect.PROJECT_WRITE, {"path": "a"}).allowed
    assert broker.authorize("delete", ToolEffect.DESTRUCTIVE, {"path": "a"}).allowed
    assert broker.authorize(
        "execute", ToolEffect.COMMAND, {"command": "pwd", "background": False}
    ).allowed
    assert [request.tool_name for request in prompts] == ["delete", "execute"]


def test_session_grant_is_conservative_and_process_local() -> None:
    prompt_count = 0

    def handler(*_args: object) -> ApprovalResponse:
        nonlocal prompt_count
        prompt_count += 1
        return ApprovalResponse(ApprovalChoice.SESSION)

    broker = PermissionBroker(ApprovalPolicy.CAUTIOUS, WorkflowState(), handler=handler)
    assert broker.authorize("write", ToolEffect.PROJECT_WRITE, {"path": "a"}).allowed
    assert broker.authorize("write", ToolEffect.PROJECT_WRITE, {"path": "a"}).allowed
    assert broker.authorize("patch", ToolEffect.PROJECT_WRITE, {"path": "a"}).allowed
    assert prompt_count == 2
    assert not PermissionBroker(ApprovalPolicy.CAUTIOUS, WorkflowState()).session_grants


def test_denial_feedback_and_abort() -> None:
    responses: Iterator[ApprovalResponse] = iter(
        [
            ApprovalResponse(ApprovalChoice.DENY, "use a safer command"),
            ApprovalResponse(ApprovalChoice.ABORT),
        ]
    )
    broker = PermissionBroker(
        ApprovalPolicy.CAUTIOUS,
        WorkflowState(),
        handler=lambda *_: next(responses),
    )

    denied = broker.authorize("execute", ToolEffect.COMMAND, {"command": "one"})
    assert not denied.allowed
    assert "safer command" in denied.message
    with pytest.raises(TurnCancelled):
        broker.authorize("execute", ToolEffect.COMMAND, {"command": "two"})


def test_wait_queue_rejects_stale_and_duplicate_responses() -> None:
    broker = PermissionBroker(ApprovalPolicy.CAUTIOUS, WorkflowState())
    request = ApprovalRequest(
        "approval_test", "write", ToolEffect.PROJECT_WRITE, {}, "summary", "key"
    )
    result: list[ApprovalResponse] = []
    thread = threading.Thread(
        target=lambda: result.append(broker.wait_for_response(request, None))
    )
    thread.start()
    while not broker.pending:
        pass
    assert broker.resolve(request.request_id, ApprovalResponse(ApprovalChoice.ONCE))
    assert not broker.resolve(request.request_id, ApprovalResponse(ApprovalChoice.DENY))
    thread.join(timeout=2)
    assert result == [ApprovalResponse(ApprovalChoice.ONCE)]
    assert not broker.resolve("stale", ApprovalResponse(ApprovalChoice.ONCE))


def test_wait_queue_is_cancellable() -> None:
    broker = PermissionBroker(ApprovalPolicy.CAUTIOUS, WorkflowState())
    request = ApprovalRequest(
        "approval_test", "write", ToolEffect.PROJECT_WRITE, {}, "summary", "key"
    )
    token = CancellationToken()
    error: list[BaseException] = []
    thread = threading.Thread(
        target=lambda: _capture_error(
            error, lambda: broker.wait_for_response(request, token)
        )
    )
    thread.start()
    while not broker.pending:
        pass
    token.cancel()
    thread.join(timeout=2)
    assert isinstance(error[0], TurnCancelled)
    assert not broker.pending


def _capture_error(errors: list[BaseException], action) -> None:
    try:
        action()
    except BaseException as error:  # noqa: BLE001
        errors.append(error)


def test_full_access_approval_cannot_bypass_read_only_sandbox(tmp_path: Path) -> None:
    sandbox = SandboxRuntime(SandboxConfig(SandboxMode.READ_ONLY, tmp_path, tmp_path))
    registry = build_tool_registry(sandbox_runtime=sandbox)
    broker = PermissionBroker(ApprovalPolicy.FULL_ACCESS, WorkflowState())

    result = registry.authorize("write", {"path": "a.txt", "content": "x"}, broker)

    assert not result.allowed
    assert "read-only" in result.message
    assert not (tmp_path / "a.txt").exists()


def test_protected_metadata_is_hard_blocked_in_danger_full_access(
    tmp_path: Path,
) -> None:
    sandbox = SandboxRuntime(
        SandboxConfig(SandboxMode.DANGER_FULL_ACCESS, tmp_path, tmp_path)
    )
    registry = build_tool_registry(sandbox_runtime=sandbox)
    broker = PermissionBroker(ApprovalPolicy.FULL_ACCESS, WorkflowState())

    result = registry.authorize(
        "write", {"path": ".git/config", "content": "x"}, broker
    )

    assert not result.allowed
    assert "protected" in result.message


def test_approval_key_distinguishes_command_mode_and_exact_command() -> None:
    foreground = approval_key(
        "execute", ToolEffect.COMMAND, {"command": "echo   one", "background": False}
    )
    background = approval_key(
        "execute", ToolEffect.COMMAND, {"command": "echo one", "background": True}
    )
    other = approval_key(
        "execute", ToolEffect.COMMAND, {"command": "echo two", "background": False}
    )
    assert len({foreground, background, other}) == 3
