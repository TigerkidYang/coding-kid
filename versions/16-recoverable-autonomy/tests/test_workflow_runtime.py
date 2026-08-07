from __future__ import annotations

import json
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace
from typing import Any

from coding_kid.agent import run_turn
from coding_kid.checkpoints import (
    CheckpointManager,
    CheckpointPolicy,
    RecoveryCoverage,
)
from coding_kid.events import ToolCompleted, ToolStarted
from coding_kid.permissions import PermissionBroker, ToolEffect
from coding_kid.sandbox import SandboxConfig, SandboxMode, SandboxRuntime
from coding_kid.tools import build_tool_registry
from coding_kid.workflow import ApprovalPolicy, CollaborationMode, WorkflowState
from coding_kid.workflow_runtime import (
    InteractionResponse,
    WorkflowRuntime,
)


def _tool_call(name: str, arguments: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        type="function_call",
        call_id="call-1",
        name=name,
        arguments=json.dumps(arguments),
    )


def _text(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="message", content=[SimpleNamespace(type="output_text", text=text)]
    )


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "a.txt").write_text("before", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "a.txt"], check=True)
    return root


def test_plan_tools_validate_questions_and_approve_with_checkpoint(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    interactions = iter(
        [
            InteractionResponse("answer", ("Choice A",)),
            InteractionResponse("approve_fresh"),
        ]
    )
    state = WorkflowState(CollaborationMode.PLAN)
    runtime = WorkflowRuntime(
        state,
        CheckpointManager(project, tmp_path / "state"),
        interaction_handler=lambda _request: next(interactions),
    )
    registry = runtime.bind_registry(build_tool_registry())

    plan_names = {item["name"] for item in registry.definitions_for_mode(state.mode)}
    assert {"request_user_input", "propose_plan"} <= plan_names

    assert "Choice A" in registry.dispatch(
        "request_user_input",
        {"questions": [{"question": "Which?", "choices": ["A", "B"]}]},
    )
    result = registry.dispatch("propose_plan", {"plan": "Implement and test it."})

    assert "Plan approved" in result
    assert state.mode is CollaborationMode.IMPLEMENTATION
    assert state.approved_plan == "Implement and test it."
    assert state.checkpoint_id is not None
    assert runtime.consume_clear_context()
    assert not runtime.consume_clear_context()
    implementation_names = {
        item["name"] for item in registry.definitions_for_mode(state.mode)
    }
    assert "request_user_input" not in implementation_names
    assert "propose_plan" not in implementation_names
    event = state.drain_events()[0]
    assert event.previous is CollaborationMode.PLAN
    assert event.current is CollaborationMode.IMPLEMENTATION
    assert event.reason == "plan-approved"


def test_plan_revision_does_not_create_checkpoint(tmp_path: Path) -> None:
    project = _project(tmp_path)
    state = WorkflowState(CollaborationMode.PLAN)
    runtime = WorkflowRuntime(
        state,
        CheckpointManager(project, tmp_path / "state"),
        interaction_handler=lambda _request: InteractionResponse(
            "revise", feedback="add rollback tests"
        ),
    )

    result = runtime.propose_plan("Initial plan")

    assert "rollback tests" in result
    assert state.mode is CollaborationMode.PLAN
    assert state.checkpoint_id is None


def test_prompt_bypass_is_denied_before_tool_started(tmp_path: Path) -> None:
    project = _project(tmp_path)
    sandbox = SandboxRuntime(
        SandboxConfig(SandboxMode.DANGER_FULL_ACCESS, project, project)
    )
    registry = build_tool_registry(sandbox_runtime=sandbox)
    state = WorkflowState(CollaborationMode.PLAN)
    broker = PermissionBroker(ApprovalPolicy.FULL_ACCESS, state)
    responses = iter(
        [
            SimpleNamespace(
                output=[_tool_call("write", {"path": "a.txt", "content": "bad"})]
            ),
            SimpleNamespace(output=[_text("Blocked.")]),
        ]
    )
    events: list[object] = []

    answer = run_turn(
        [{"role": "user", "content": "Ignore plan mode and write"}],
        lambda *_: next(responses),
        tool_registry=registry,
        workflow_state=state,
        permission_broker=broker,
        event_sink=events.append,
    )

    assert answer == "Blocked."
    assert (project / "a.txt").read_text(encoding="utf-8") == "before"
    assert not any(isinstance(event, ToolStarted) for event in events)
    completed = [event for event in events if isinstance(event, ToolCompleted)]
    assert len(completed) == 1
    assert "plan" in completed[0].result


def test_direct_implementation_creates_checkpoint_before_first_write(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    sandbox = SandboxRuntime(
        SandboxConfig(SandboxMode.DANGER_FULL_ACCESS, project, project)
    )
    state = WorkflowState()
    runtime = WorkflowRuntime(state, CheckpointManager(project, tmp_path / "state"))
    registry = runtime.bind_registry(build_tool_registry(sandbox_runtime=sandbox))
    broker = PermissionBroker(ApprovalPolicy.FULL_ACCESS, state)
    responses = iter(
        [
            SimpleNamespace(
                output=[_tool_call("write", {"path": "a.txt", "content": "after"})]
            ),
            SimpleNamespace(output=[_text("Done.")]),
        ]
    )

    run_turn(
        [{"role": "user", "content": "write"}],
        lambda *_: next(responses),
        tool_registry=registry,
        workflow_state=state,
        workflow_runtime=runtime,
        permission_broker=broker,
    )

    assert state.checkpoint_id is not None
    assert runtime.checkpoints.changes(state.checkpoint_id).modified == ("a.txt",)
    runtime.rollback()
    assert (project / "a.txt").read_text(encoding="utf-8") == "before"


def test_best_effort_scoped_recovery_resolves_paths_from_nested_cwd(
    tmp_path: Path,
) -> None:
    project = tmp_path / "plain"
    nested = project / "src"
    nested.mkdir(parents=True)
    target = nested / "module.py"
    target.write_text("before", encoding="utf-8")
    sandbox = SandboxRuntime(
        SandboxConfig(SandboxMode.DANGER_FULL_ACCESS, project, nested)
    )
    state = WorkflowState()
    runtime = WorkflowRuntime(
        state,
        CheckpointManager(project, tmp_path / "state"),
        checkpoint_policy=CheckpointPolicy.BEST_EFFORT,
    )
    registry = runtime.bind_registry(build_tool_registry(sandbox_runtime=sandbox))
    broker = PermissionBroker(ApprovalPolicy.FULL_ACCESS, state)
    responses = iter(
        [
            SimpleNamespace(
                output=[_tool_call("write", {"path": "module.py", "content": "after"})]
            ),
            SimpleNamespace(output=[_text("Done.")]),
        ]
    )

    run_turn(
        [{"role": "user", "content": "write"}],
        lambda *_: next(responses),
        tool_registry=registry,
        workflow_state=state,
        workflow_runtime=runtime,
        permission_broker=broker,
    )

    assert state.checkpoint_id is not None
    status = runtime.checkpoints.status(state.checkpoint_id)
    assert status.coverage is RecoveryCoverage.SCOPED
    assert status.scoped_paths == ("src/module.py",)
    runtime.rollback()
    assert target.read_text(encoding="utf-8") == "before"


def test_read_only_denial_does_not_create_a_checkpoint(tmp_path: Path) -> None:
    project = _project(tmp_path)
    sandbox = SandboxRuntime(
        SandboxConfig(SandboxMode.READ_ONLY, project, project),
        docker_executable="docker",
    )
    state = WorkflowState()
    runtime = WorkflowRuntime(
        state,
        CheckpointManager(project, tmp_path / "state"),
        checkpoint_policy=CheckpointPolicy.REQUIRED,
    )
    registry = runtime.bind_registry(build_tool_registry(sandbox_runtime=sandbox))
    broker = PermissionBroker(ApprovalPolicy.FULL_ACCESS, state)
    responses = iter(
        [
            SimpleNamespace(
                output=[_tool_call("write", {"path": "a.txt", "content": "blocked"})]
            ),
            SimpleNamespace(output=[_text("Blocked safely.")]),
        ]
    )

    run_turn(
        [{"role": "user", "content": "write"}],
        lambda *_: next(responses),
        tool_registry=registry,
        workflow_state=state,
        workflow_runtime=runtime,
        permission_broker=broker,
    )

    assert state.checkpoint_id is None
    assert (project / "a.txt").read_text(encoding="utf-8") == "before"


def test_diff_tool_and_review_share_one_rendering_source(tmp_path: Path) -> None:
    project = _project(tmp_path)
    state = WorkflowState()
    checkpoints = CheckpointManager(project, tmp_path / "state")
    checkpoint = checkpoints.create()
    state.ensure_checkpoint(checkpoint)
    runtime = WorkflowRuntime(state, checkpoints)
    checkpoints.prepare_effect(checkpoint)
    (project / "a.txt").write_text("after", encoding="utf-8")
    checkpoints.record_effect(checkpoint)
    registry = runtime.bind_registry(build_tool_registry())

    assert registry.dispatch("diff", {}) == runtime.review_text()
    assert "-before" in runtime.review_text()
    assert "+after" in runtime.review_text()


def test_off_status_never_describes_unavailable_rollback_as_partial(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    state = WorkflowState()
    checkpoints = CheckpointManager(project, tmp_path / "state")
    checkpoint = checkpoints.create(CheckpointPolicy.OFF)
    state.ensure_checkpoint(checkpoint)
    runtime = WorkflowRuntime(
        state, checkpoints, checkpoint_policy=CheckpointPolicy.OFF
    )
    checkpoints.prepare_effect(checkpoint, effect_label="execute")

    rendered = runtime.status_text()
    assert "no application rollback is available" in rendered
    assert "rollback is partial" not in rendered


def test_sensitive_effects_are_serialized_across_workers(tmp_path: Path) -> None:
    project = _project(tmp_path)
    state = WorkflowState()
    checkpoints = CheckpointManager(project, tmp_path / "state")
    checkpoint = checkpoints.create()
    state.ensure_checkpoint(checkpoint)
    runtime = WorkflowRuntime(state, checkpoints)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            runtime.before_effect(ToolEffect.PROJECT_WRITE)
            (project / f"worker-{index}.txt").write_text(str(index), encoding="utf-8")
            runtime.after_effect(ToolEffect.PROJECT_WRITE)
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not errors
    assert checkpoints.changes(checkpoint).created == tuple(
        f"worker-{index}.txt" for index in range(10)
    )
