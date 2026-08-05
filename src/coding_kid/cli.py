"""The plain terminal interface for Coding Kid."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import inspect
import sys
from typing import Any

from coding_kid.agent import current_instructions, run_turn
from coding_kid.agents import AgentEvent, AgentManager
from coding_kid.background_tasks import BackgroundTaskManager, TaskEvent
from coding_kid.capabilities import CapabilityRuntime
from coding_kid.checkpoints import CheckpointManager
from coding_kid.compaction import compact_context
from coding_kid.context import SessionContext
from coding_kid.context_manager import ContextManager
from coding_kid.memory import MemoryManager
from coding_kid.permissions import (
    ApprovalChoice,
    ApprovalRequest,
    ApprovalResponse,
    PermissionBroker,
    ToolEffect,
)
from coding_kid.provider import generate
from coding_kid.sandbox import (
    DEFAULT_SANDBOX_IMAGE,
    SandboxConfig,
    SandboxMode,
    SandboxRuntime,
)
from coding_kid.sessions import SessionError, SessionHandle, SessionInfo, SessionStore
from coding_kid.skills import SkillTurnState, explicit_skill_names
from coding_kid.tools import TodoState, build_tool_registry
from coding_kid.workflow import ApprovalPolicy, CollaborationMode, WorkflowState
from coding_kid.workflow_runtime import (
    InteractionRequest,
    InteractionResponse,
    WorkflowRuntime,
)
from coding_kid.web import WebRuntime
from coding_kid.worktrees import WorktreeError, WorktreeManager

InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]
MAX_TOOL_DISPLAY_CHARS = 140


def _worktree_manager(handle: SessionHandle) -> WorktreeManager | None:
    """Enable isolation only when the captured project is a valid Git worktree."""
    try:
        return WorktreeManager(
            handle.context.project_root,
            handle.store.project_dir / "worktrees",
        )
    except WorktreeError:
        return None


def _safe_output_function(output_function: OutputFunction) -> OutputFunction:
    """Keep display encoding failures from aborting an Agent turn."""

    def output(text: str) -> None:
        try:
            output_function(text)
        except UnicodeEncodeError as error:
            safe_text = text.encode(error.encoding, errors="backslashreplace").decode(
                error.encoding
            )
            output_function(safe_text)

    return output


def _configure_standard_output() -> None:
    """Use UTF-8 for redirected Windows output as well as real consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


@dataclass(frozen=True)
class SessionOptions:
    """Session lifecycle choice parsed by the version-selecting launcher."""

    mode: str = "new"
    session_id: str | None = None
    list_only: bool = False
    delete_session: str | None = None
    sandbox_mode: str = SandboxMode.WORKSPACE_WRITE.value
    sandbox_image: str = DEFAULT_SANDBOX_IMAGE
    sandbox_network: bool = False
    collaboration_mode: str = CollaborationMode.IMPLEMENTATION.value
    approval_policy: str = ApprovalPolicy.CAUTIOUS.value


def format_tool_call(name: str, arguments: dict[str, Any]) -> str:
    """Describe a tool action without exposing its input or output contents."""
    if name == "execute":
        rendered = f"[tool] execute: {arguments.get('command', '?')}"
    elif name == "search":
        query = arguments.get("query", "?")
        path = arguments.get("path") or "."
        rendered = f'[tool] search: "{query}" in {path}'
    elif name in {"read", "write", "patch", "delete"}:
        rendered = f"[tool] {name}: {arguments.get('path', '?')}"
    elif name == "todo":
        items = arguments.get("todos")
        if not isinstance(items, list):
            rendered = "[tool] todo"
        else:
            in_progress = sum(
                1
                for item in items
                if isinstance(item, dict) and item.get("status") == "in_progress"
            )
            completed = sum(
                1
                for item in items
                if isinstance(item, dict) and item.get("status") == "completed"
            )
            rendered = (
                f"[tool] todo: {len(items)} items "
                f"({in_progress} in progress, {completed} done)"
            )
    elif name == "task":
        action = arguments.get("action", "?")
        task_id = arguments.get("task_id")
        suffix = f" {task_id}" if task_id else ""
        rendered = f"[tool] task {action}{suffix}"
    elif name == "spawn_agent":
        rendered = f"[tool] spawn Agent: {arguments.get('description', '?')}"
    elif name == "agent":
        action = arguments.get("action", "?")
        agent_id = arguments.get("agent_id")
        suffix = f" {agent_id}" if agent_id else ""
        rendered = f"[tool] Agent {action}{suffix}"
    else:
        rendered = f"[tool] {name}"

    rendered = " ".join(str(rendered).splitlines())
    if len(rendered) > MAX_TOOL_DISPLAY_CHARS:
        return f"{rendered[: MAX_TOOL_DISPLAY_CHARS - 3]}..."
    return rendered


def chat(
    input_function: InputFunction = input,
    output_function: OutputFunction = print,
    *,
    session_handle: SessionHandle | None = None,
    memory_manager: MemoryManager | None = None,
    capability_runtime: CapabilityRuntime | None = None,
    background_tasks: BackgroundTaskManager | None = None,
    todo_state: TodoState | None = None,
    agent_manager: AgentManager | None = None,
    sandbox_runtime: SandboxRuntime | None = None,
    permission_broker: PermissionBroker | None = None,
    workflow_runtime: WorkflowRuntime | None = None,
    web_runtime: WebRuntime | None = None,
) -> None:
    """Keep accepting user messages until the user exits."""
    output_function = _safe_output_function(output_function)
    owns_background_tasks = background_tasks is None
    background_tasks = background_tasks or BackgroundTaskManager(
        sandbox_runtime=sandbox_runtime
    )
    owns_agent_manager = agent_manager is None
    if session_handle is None:
        try:
            session_context = SessionContext.capture()
            manager = ContextManager.capture(session_context)
        except RuntimeError as error:
            output_function(f"Error: {error}")
            return
        todo_state = todo_state or TodoState()
        ready = "Coding Kid is ready. Type /exit to quit."
    else:
        session_context = session_handle.context
        manager = session_handle.manager
        todo_state = todo_state or TodoState(session_handle.todos)
        ready = (
            f"Coding Kid is ready. Session {session_handle.info.session_id[:8]}. "
            "Type /exit to quit."
        )
    agent_manager = agent_manager or AgentManager(
        session_context,
        manager.budget,
        capability_runtime=capability_runtime,
        sandbox_runtime=sandbox_runtime,
        permission_broker=permission_broker,
        workflow_state=(workflow_runtime.state if workflow_runtime else None),
        workflow_runtime=workflow_runtime,
        root_manager=manager,
        workspace_manager=(
            _worktree_manager(session_handle) if session_handle is not None else None
        ),
        web_runtime=web_runtime,
    )
    workflow_state = (
        workflow_runtime.state
        if workflow_runtime is not None
        else session_handle.workflow
        if session_handle is not None
        else WorkflowState()
    )
    if permission_broker is not None:
        permission_broker.set_handler(
            lambda request, token: _cli_approval(
                request, token, input_function, output_function
            )
        )
    if workflow_runtime is not None:
        workflow_runtime.set_interaction_handler(
            lambda request: _cli_interaction(request, input_function, output_function)
        )
    output_function(ready)
    if sandbox_runtime is not None:
        output_function(sandbox_runtime.status_text())
    output_function(
        _permissions_text(workflow_state, permission_broker, sandbox_runtime)
    )
    if capability_runtime is not None:
        output_function(capability_runtime.summary())
        for warning in capability_runtime.warnings:
            output_function(f"[capability] warning: {warning}")
    if web_runtime is not None:
        output_function(web_runtime.status_text())
    if (
        memory_manager is not None
        and memory_manager.mode == "auto"
        and session_handle is not None
    ):
        output_function("[memory] checking eligible prior sessions")
        result = memory_manager.sync(
            generate,
            current_session_id=session_handle.info.session_id,
        )
        output_function(_format_memory_sync(result))

    def show_tool(name: str, arguments: dict[str, Any], result: str) -> None:
        output_function(format_tool_call(name, arguments))
        if result.startswith("ERROR:"):
            output_function(result)

    def show_context(message: str) -> None:
        output_function(message)

    while True:
        for event in agent_manager.drain_events():
            output_function(_format_agent_event(event))
        for event in background_tasks.drain_events():
            if event.status != "running":
                output_function(_format_task_event(event))
        try:
            user_input = input_function("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            output_function("\nGoodbye.")
            break

        if user_input in {"/exit", "/quit"}:
            output_function("Goodbye.")
            break
        if not user_input:
            continue
        if user_input == "/tasks":
            output_function(background_tasks.status_text())
            continue
        if user_input == "/agents":
            output_function(agent_manager.status_text())
            continue
        if user_input == "/sandbox":
            output_function(
                sandbox_runtime.status_text()
                if sandbox_runtime is not None
                else "Sandbox: not configured"
            )
            continue
        if user_input == "/permissions":
            output_function(
                _permissions_text(workflow_state, permission_broker, sandbox_runtime)
            )
            continue
        if user_input == "/mode":
            output_function(f"Workflow mode: {workflow_state.mode.value}")
            continue
        if user_input.startswith("/mode "):
            value = user_input.removeprefix("/mode ").strip()
            try:
                mode = CollaborationMode(value)
                workflow_state.transition(mode)
                _commit_workflow_state(session_handle, todo_state)
            except (ValueError, SessionError) as error:
                output_function(f"Error: {error}")
            else:
                output_function(f"Workflow mode: {mode.value}")
                if mode is CollaborationMode.REVIEW and workflow_runtime is not None:
                    output_function(workflow_runtime.review_text())
            continue
        if user_input == "/changes":
            output_function(
                workflow_runtime.status_text()
                if workflow_runtime is not None
                else "Change workflow is not active."
            )
            continue
        if user_input == "/changes accept":
            if workflow_runtime is None:
                output_function("Change workflow is not active.")
            else:
                try:
                    changes = workflow_runtime.accept()
                    _commit_workflow_state(session_handle, todo_state)
                except Exception as error:  # noqa: BLE001
                    output_function(f"Error: {error}")
                else:
                    output_function(f"Accepted stage changes.\n{changes.text()}")
            continue
        if user_input == "/changes rollback":
            if workflow_runtime is None:
                output_function("Change workflow is not active.")
            else:
                try:
                    changes = workflow_runtime.rollback()
                    _commit_workflow_state(session_handle, todo_state)
                except Exception as error:  # noqa: BLE001
                    output_function(f"Error: {error}")
                else:
                    output_function(f"Rolled back stage changes.\n{changes.text()}")
            continue
        if user_input.startswith("/agent "):
            parts = user_input.split()
            action = parts[1] if len(parts) > 1 else ""
            if action in {"diff", "integrate", "reconcile", "discard"}:
                if len(parts) < 3:
                    output_function(f"Usage: /agent {action} <id>")
                    continue
                agent_id = parts[2]
                confirmed = len(parts) == 4 and parts[3] == "--confirm"
                if action == "discard" and not confirmed:
                    output_function("Usage: /agent discard <id> --confirm")
                    continue
                effect = (
                    ToolEffect.READ_ONLY if action == "diff" else ToolEffect.DESTRUCTIVE
                )
                prepared = False
                try:
                    if workflow_runtime is not None:
                        workflow_runtime.before_effect(effect)
                        prepared = effect is ToolEffect.DESTRUCTIVE
                    if action == "diff":
                        rendered = agent_manager.diff(agent_id)
                    elif action == "integrate":
                        rendered = agent_manager.integrate(agent_id).model_text()
                    elif action == "reconcile":
                        rendered = agent_manager.reconcile(agent_id).model_text()
                    else:
                        rendered = agent_manager.discard(
                            agent_id, confirmed=confirmed
                        ).model_text()
                except Exception as error:
                    output_function(f"Error: {error}")
                else:
                    output_function(rendered)
                finally:
                    if prepared and workflow_runtime is not None:
                        try:
                            workflow_runtime.after_effect(effect)
                        except Exception as error:
                            output_function(f"Error: {error}")
                continue
        if user_input.startswith("/agent stop "):
            agent_id = user_input.removeprefix("/agent stop ").strip()
            try:
                result = agent_manager.stop(agent_id)
            except Exception as error:
                output_function(f"Error: {error}")
            else:
                output_function(f"Agent {result.agent_id}: {result.status}.")
                agent_manager.drain_events()
            continue
        if user_input.startswith("/task poll "):
            task_id = user_input.removeprefix("/task poll ").strip()
            try:
                result = background_tasks.poll(task_id, incremental=True)
            except Exception as error:
                output_function(f"Error: {error}")
            else:
                output_function(result.model_text())
            continue
        if user_input.startswith("/task input "):
            parts = user_input.split(maxsplit=3)
            if len(parts) < 4:
                output_function("Usage: /task input <id> <text>")
                continue
            try:
                result = background_tasks.write(parts[2], parts[3])
            except Exception as error:
                output_function(f"Error: {error}")
            else:
                output_function(result.model_text())
            continue
        if user_input.startswith("/task interrupt "):
            task_id = user_input.removeprefix("/task interrupt ").strip()
            try:
                result = background_tasks.interrupt(task_id)
            except Exception as error:
                output_function(f"Error: {error}")
            else:
                output_function(result.model_text())
            continue
        if user_input.startswith("/task check "):
            parts = user_input.split(maxsplit=3)
            if len(parts) < 4:
                output_function("Usage: /task check <id> <command>")
                continue
            try:
                result = background_tasks.check(parts[2], parts[3])
            except Exception as error:
                output_function(f"Error: {error}")
            else:
                output_function("Readiness check evidence:\n" + result.model_text())
            continue
        if user_input.startswith("/task stop "):
            task_id = user_input.removeprefix("/task stop ").strip()
            try:
                result = background_tasks.stop(task_id)
            except Exception as error:
                output_function(f"Error: {error}")
            else:
                output_function(
                    f"Stopped {result.task_id} ({result.status}, "
                    f"exit {result.exit_code})."
                )
                background_tasks.drain_events()
            continue
        if user_input == "/context":
            base_registry = build_tool_registry(
                background_tasks,
                todo_state=todo_state,
                agent_manager=agent_manager,
                sandbox_runtime=sandbox_runtime,
                web_runtime=web_runtime,
            )
            definitions = base_registry.definitions()
            context_overlays: tuple[str, ...] = (
                (sandbox_runtime.instruction_text(),)
                if sandbox_runtime is not None
                else ()
            )
            if capability_runtime is not None:
                definitions = capability_runtime.registry_for_turn(
                    SkillTurnState(capability_runtime.snapshot.skills),
                    base_registry=base_registry,
                ).definitions()
                metadata = capability_runtime.skill_metadata()
                if metadata:
                    context_overlays = (*context_overlays, metadata)
            output_function(
                manager.status_text(
                    current_instructions(session_context, context_overlays, todo_state),
                    definitions,
                )
            )
            continue
        if user_input == "/capabilities":
            output_function(
                capability_runtime.status_text()
                if capability_runtime is not None
                else "Pluggable capabilities are not active."
            )
            continue
        if user_input == "/session":
            if session_handle is None:
                output_function("Session: ephemeral")
            else:
                output_function(_format_session(session_handle.info))
            continue
        if user_input == "/session save":
            if session_handle is None:
                output_function("Session persistence is not active.")
            else:
                try:
                    session_handle.retry_save()
                except Exception as error:
                    output_function(f"Fatal persistence error: {error}")
                else:
                    output_function("Session state is durable.")
            continue
        if user_input == "/sessions":
            if session_handle is None:
                output_function("Session persistence is not active.")
            else:
                output_function(_format_sessions(session_handle.store.list_sessions()))
            continue
        if user_input == "/memory":
            output_function(
                memory_manager.status_text()
                if memory_manager is not None
                else "Long-term memory is not active."
            )
            continue
        if user_input.startswith("/memory search "):
            if memory_manager is None:
                output_function("Long-term memory is not active.")
            else:
                output_function(
                    _format_memories(
                        memory_manager.search(
                            user_input.removeprefix("/memory search ")
                        )
                    )
                )
            continue
        if user_input == "/memory sync":
            if memory_manager is None or session_handle is None:
                output_function("Long-term memory is not active.")
            else:
                output_function("[memory] synchronizing")
                output_function(
                    _format_memory_sync(
                        memory_manager.sync(
                            generate,
                            current_session_id=session_handle.info.session_id,
                            force=True,
                        )
                    )
                )
            continue
        if user_input.startswith("/remember "):
            if memory_manager is None:
                output_function("Long-term memory is not active.")
            else:
                content = user_input.removeprefix("/remember ")
                global_scope = content.startswith("--global ")
                if global_scope:
                    content = content.removeprefix("--global ")
                try:
                    entry = memory_manager.add(content, global_scope=global_scope)
                except SessionError as error:
                    output_function(f"Error: {error}")
                else:
                    output_function(
                        f"Remembered {entry.memory_id[:8]} ({entry.scope})."
                    )
            continue
        if user_input.startswith("/forget "):
            if memory_manager is None:
                output_function("Long-term memory is not active.")
            else:
                try:
                    entry = memory_manager.forget(user_input.removeprefix("/forget "))
                except SessionError as error:
                    output_function(f"Error: {error}")
                else:
                    output_function(f"Forgot memory {entry.memory_id[:8]}.")
            continue
        if session_handle is not None and session_handle.dirty:
            output_function(
                "Persistence is pending. Use /session save before continuing."
            )
            continue
        if user_input == "/compact":
            snapshot = manager.clone()
            base_registry = build_tool_registry(
                background_tasks,
                todo_state=todo_state,
                agent_manager=agent_manager,
                sandbox_runtime=sandbox_runtime,
                web_runtime=web_runtime,
            )
            definitions = base_registry.definitions()
            compact_overlays: tuple[str, ...] = (
                (sandbox_runtime.instruction_text(),)
                if sandbox_runtime is not None
                else ()
            )
            if capability_runtime is not None:
                definitions = capability_runtime.registry_for_turn(
                    SkillTurnState(capability_runtime.snapshot.skills),
                    base_registry=base_registry,
                ).definitions()
                metadata = capability_runtime.skill_metadata()
                if metadata:
                    compact_overlays = (*compact_overlays, metadata)
            try:
                compact_context(
                    manager,
                    generate,
                    instructions=current_instructions(
                        session_context, compact_overlays, todo_state
                    ),
                    tools=definitions,
                    trigger="manual",
                    on_context=show_context,
                )
            except KeyboardInterrupt:
                manager.restore(snapshot)
                output_function("\nCompaction interrupted.")
            except Exception as error:
                manager.restore(snapshot)
                output_function(f"Error: {error}")
            else:
                if session_handle is not None:
                    session_handle.todos = todo_state.items
                    try:
                        session_handle.commit_state(kind="context_committed")
                    except Exception as error:
                        output_function(f"Fatal persistence error: {error}")
                        continue
            continue

        request_context: list[Any] = []
        recalled_ids: tuple[str, ...] = ()
        if memory_manager is not None:
            request_context, recalled_ids = memory_manager.recall_context(user_input)
        skill_state: SkillTurnState | None = None
        registry = build_tool_registry(
            background_tasks,
            todo_state=todo_state,
            agent_manager=agent_manager,
            sandbox_runtime=sandbox_runtime,
            web_runtime=web_runtime,
        )
        if workflow_runtime is not None:
            registry = workflow_runtime.bind_registry(registry)
        if (
            workflow_runtime is not None
            and workflow_state.mode is CollaborationMode.REVIEW
        ):
            request_context.append(
                {"role": "user", "content": workflow_runtime.review_text()}
            )
        overlays: tuple[str, ...] = (
            (sandbox_runtime.instruction_text(),) if sandbox_runtime is not None else ()
        )
        if capability_runtime is not None:
            skill_state = SkillTurnState(capability_runtime.snapshot.skills)
            for skill_name in explicit_skill_names(
                user_input, capability_runtime.snapshot.skills
            ):
                request_context.append(
                    {
                        "role": "user",
                        "content": capability_runtime.load_skill(
                            skill_state, skill_name, explicit=True
                        ),
                    }
                )
            registry = capability_runtime.registry_for_turn(
                skill_state,
                base_registry=registry,
            )
            metadata = capability_runtime.skill_metadata()
            if metadata:
                overlays = (*overlays, metadata)
        manager.conversation.append_user(user_input)
        try:
            turn_options: dict[str, Any] = {}
            if memory_manager is not None:
                turn_options = {
                    "request_context": request_context,
                    "on_memory_citations": lambda cited: memory_manager.record_usage(
                        set(cited) & set(recalled_ids)
                    ),
                }
            parameters = inspect.signature(run_turn).parameters
            if "tool_registry" in parameters:
                turn_options["tool_registry"] = registry
            if "background_tasks" in parameters:
                turn_options["background_tasks"] = background_tasks
            if "todo_state" in parameters:
                turn_options["todo_state"] = todo_state
            if "agent_manager" in parameters:
                turn_options["agent_manager"] = agent_manager
            if permission_broker is not None:
                turn_options["permission_broker"] = permission_broker
            if workflow_runtime is not None:
                turn_options["workflow_state"] = workflow_state
                turn_options["workflow_runtime"] = workflow_runtime
            if capability_runtime is not None and "instruction_overlays" in parameters:
                turn_options["instruction_overlays"] = overlays
            answer = run_turn(
                manager,
                on_tool=show_tool,
                on_context=show_context,
                session_context=session_context,
                **turn_options,
            )
            if not answer.strip():
                raise RuntimeError("Model returned an empty answer")
        except KeyboardInterrupt:
            if session_handle is not None:
                session_handle.todos = todo_state.items
                try:
                    session_handle.commit_state(kind="turn_interrupted")
                except Exception as error:
                    output_function(f"Persistence warning: {error}")
            output_function(
                "\nTask interrupted. Completed work was retained; you can enter "
                "another request."
            )
            continue
        except Exception as error:
            if session_handle is not None:
                session_handle.todos = todo_state.items
                try:
                    session_handle.commit_state(kind="turn_failed")
                except Exception as persistence_error:
                    output_function(f"Persistence warning: {persistence_error}")
            output_function(f"Error: {error}")
            continue

        if session_handle is not None:
            session_handle.todos = todo_state.items
            try:
                session_handle.commit_state()
            except Exception as error:
                output_function(f"Coding Kid> {answer}")
                output_function(
                    "Fatal persistence error: the completed turn remains in memory "
                    f"but is not durable: {error}"
                )
                continue

        output_function(f"Coding Kid> {answer}")

    if owns_agent_manager:
        agent_manager.close()
    if owns_background_tasks:
        background_tasks.close()


def _format_session(info: SessionInfo) -> str:
    marker = " damaged" if info.damaged else ""
    return (
        f"{info.session_id[:8]}  {info.status}{marker}  {info.model}  "
        f"{info.updated_at}  {info.title}"
    )


def _permissions_text(
    workflow: WorkflowState,
    broker: PermissionBroker | None,
    sandbox: SandboxRuntime | None,
) -> str:
    approval = broker.policy.value if broker is not None else "not configured"
    sandbox_mode = (
        sandbox.config.mode.value if sandbox is not None else "not configured"
    )
    grants = len(broker.session_grants) if broker is not None else 0
    return (
        f"Workflow mode: {workflow.mode.value}\n"
        f"Approval policy: {approval}\n"
        f"Sandbox policy: {sandbox_mode}\n"
        f"Session grants: {grants}"
    )


def _commit_workflow_state(
    session_handle: SessionHandle | None, todo_state: TodoState
) -> None:
    if session_handle is None:
        return
    session_handle.todos = todo_state.items
    session_handle.commit_state(kind="workflow_committed")


def _cli_approval(
    request: ApprovalRequest,
    cancellation_token: Any,
    input_function: InputFunction,
    output_function: OutputFunction,
) -> ApprovalResponse:
    output_function(
        f"[approval] {request.tool_name} ({request.effect.value})\n{request.summary}\n"
        "1. Approve once  2. Approve matching action for this session  "
        "3. Deny  4. Abort turn"
    )
    while True:
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()
        try:
            choice = input_function("Approval> ").strip()
        except (EOFError, KeyboardInterrupt):
            return ApprovalResponse(ApprovalChoice.DENY, "Approval input unavailable")
        if choice == "1":
            return ApprovalResponse(ApprovalChoice.ONCE)
        if choice == "2":
            return ApprovalResponse(ApprovalChoice.SESSION)
        if choice == "3":
            try:
                feedback = input_function("Feedback (optional)> ").strip() or None
            except (EOFError, KeyboardInterrupt):
                feedback = None
            return ApprovalResponse(ApprovalChoice.DENY, feedback)
        if choice == "4":
            return ApprovalResponse(ApprovalChoice.ABORT)
        output_function("Choose 1, 2, 3, or 4.")


def _cli_interaction(
    request: InteractionRequest,
    input_function: InputFunction,
    output_function: OutputFunction,
) -> InteractionResponse:
    if request.kind == "questions":
        answers: list[str] = []
        for item in request.payload["questions"]:
            output_function(item["question"])
            output_function(
                "  ".join(
                    f"{index}. {choice}"
                    for index, choice in enumerate(item["choices"], start=1)
                )
            )
            try:
                value = input_function("Answer> ").strip()
            except (EOFError, KeyboardInterrupt):
                return InteractionResponse("abort")
            try:
                answer = item["choices"][int(value) - 1]
            except (ValueError, IndexError):
                answer = value
            answers.append(answer)
        return InteractionResponse("answer", tuple(answers))
    output_function(f"[proposed plan]\n{request.payload['plan']}")
    output_function(
        "1. Approve and keep context  2. Approve with fresh context  "
        "3. Continue planning with feedback"
    )
    try:
        choice = input_function("Plan> ").strip()
    except (EOFError, KeyboardInterrupt):
        return InteractionResponse("revise", feedback="Plan approval unavailable")
    if choice == "1":
        return InteractionResponse("approve")
    if choice == "2":
        return InteractionResponse("approve_fresh")
    try:
        feedback = input_function("Feedback> ").strip()
    except (EOFError, KeyboardInterrupt):
        feedback = "Continue planning."
    return InteractionResponse("revise", feedback=feedback)


def _format_task_event(event: TaskEvent) -> str:
    suffix = f", exit {event.exit_code}" if event.exit_code is not None else ""
    return f"[task] {event.task_id} {event.status}{suffix}: {event.command}"


def _format_agent_event(event: AgentEvent) -> str:
    status = "started" if event.status == "starting" else event.status
    return (
        f"[agent] {event.agent_id} {status} "
        f"(turn {event.turn_count}): {event.description}"
    )


def _format_sessions(items: list[SessionInfo]) -> str:
    if not items:
        return "No sessions for this project."
    return "\n".join(_format_session(item) for item in items)


def _format_memories(items: list[Any]) -> str:
    if not items:
        return "No matching memories."
    return "\n".join(
        f"{item.memory_id[:8]}  {item.scope}/{item.type}  {item.title}"
        for item in items
    )


def _format_memory_sync(result: Any) -> str:
    if result.error:
        return f"[memory] failed: {result.error}"
    return (
        f"[memory] extracted {result.extracted_sessions} session(s); "
        f"consolidated {result.consolidated_memories} memory item(s)"
    )


def _open_session(
    options: SessionOptions,
    current_context: SessionContext | None = None,
    store: SessionStore | None = None,
) -> SessionHandle:
    current = current_context or SessionContext.capture()
    session_store = store or SessionStore(current.project_root)
    if options.mode == "continue":
        handle = session_store.continue_latest()
    elif options.mode == "resume" and options.session_id:
        handle = session_store.resume(options.session_id)
    else:
        manager = ContextManager.capture(current)
        handle = session_store.create(
            current,
            manager,
            [],
            WorkflowState(CollaborationMode(options.collaboration_mode)),
        )
    if handle.context.cwd != current.cwd:
        handle.close()
        raise SessionError(
            f"Resume from the session's original directory: {handle.context.cwd}"
        )
    if handle.context.model != current.model:
        handle.close()
        raise SessionError(
            "Resume with the session's original OPENROUTER_MODEL: "
            f"{handle.context.model}"
        )
    return handle


def _create_sandbox(
    options: SessionOptions,
    context: SessionContext,
) -> SandboxRuntime:
    runtime = SandboxRuntime(
        SandboxConfig(
            SandboxMode(options.sandbox_mode),
            context.project_root,
            context.cwd,
            options.sandbox_image,
            options.sandbox_network,
        )
    )
    runtime.check_available()
    return runtime


def main(options: SessionOptions | None = None) -> None:
    """Start the terminal chat."""
    _configure_standard_output()
    selection = options or SessionOptions()
    try:
        current_context = SessionContext.capture()
        store = SessionStore(current_context.project_root)
        if selection.list_only:
            print(_format_sessions(store.list_sessions()))
            return
        if selection.delete_session:
            deleted = store.soft_delete(selection.delete_session)
            print(f"Deleted session {deleted.session_id[:8]} (evidence retained).")
            return
        sandbox_runtime = _create_sandbox(selection, current_context)
        handle = _open_session(selection, current_context, store)
    except (RuntimeError, ValueError) as error:
        print(f"Error: {error}")
        return

    try:
        memory_manager = MemoryManager(handle.store)
        background_tasks = BackgroundTaskManager(sandbox_runtime=sandbox_runtime)
        capability_runtime = CapabilityRuntime.capture(
            handle.context,
            context_window=handle.manager.budget.context_length,
            external_tools_enabled=not sandbox_runtime.restricted,
        )
        web_runtime = WebRuntime()
        managers: dict[str, Any] = {"background": background_tasks}
        checkpoint_manager = CheckpointManager(
            handle.context.project_root,
            handle.store.project_dir / "checkpoints",
            running_tasks=lambda: managers["background"].running_count,
            running_agents=lambda: (
                managers["agent"].running_count if "agent" in managers else 0
            ),
        )
        workflow_runtime = WorkflowRuntime(handle.workflow, checkpoint_manager)
        permission_broker = PermissionBroker(
            ApprovalPolicy(selection.approval_policy), handle.workflow
        )
        agent_manager = AgentManager(
            handle.context,
            handle.manager.budget,
            capability_runtime=capability_runtime,
            sandbox_runtime=sandbox_runtime,
            permission_broker=permission_broker,
            workflow_state=handle.workflow,
            workflow_runtime=workflow_runtime,
            root_manager=handle.manager,
            workspace_manager=_worktree_manager(handle),
            web_runtime=web_runtime,
        )
        managers["agent"] = agent_manager
        if sys.stdin.isatty() and sys.stdout.isatty():
            from coding_kid.tui import run_tui

            tui_options: dict[str, Any] = {
                "session_handle": handle,
                "memory_manager": memory_manager,
            }
            if "permission_broker" in inspect.signature(run_tui).parameters:
                tui_options["permission_broker"] = permission_broker
            if "workflow_runtime" in inspect.signature(run_tui).parameters:
                tui_options["workflow_runtime"] = workflow_runtime
            if "sandbox_runtime" in inspect.signature(run_tui).parameters:
                tui_options["sandbox_runtime"] = sandbox_runtime
            if "background_tasks" in inspect.signature(run_tui).parameters:
                tui_options["background_tasks"] = background_tasks
            if "capability_runtime" in inspect.signature(run_tui).parameters:
                tui_options["capability_runtime"] = capability_runtime
            if "agent_manager" in inspect.signature(run_tui).parameters:
                tui_options["agent_manager"] = agent_manager
            if "web_runtime" in inspect.signature(run_tui).parameters:
                tui_options["web_runtime"] = web_runtime
            run_tui(handle.context, handle.manager, **tui_options)
        else:
            chat_options: dict[str, Any] = {
                "session_handle": handle,
                "memory_manager": memory_manager,
            }
            if "permission_broker" in inspect.signature(chat).parameters:
                chat_options["permission_broker"] = permission_broker
            if "workflow_runtime" in inspect.signature(chat).parameters:
                chat_options["workflow_runtime"] = workflow_runtime
            if "sandbox_runtime" in inspect.signature(chat).parameters:
                chat_options["sandbox_runtime"] = sandbox_runtime
            if "background_tasks" in inspect.signature(chat).parameters:
                chat_options["background_tasks"] = background_tasks
            if "capability_runtime" in inspect.signature(chat).parameters:
                chat_options["capability_runtime"] = capability_runtime
            if "agent_manager" in inspect.signature(chat).parameters:
                chat_options["agent_manager"] = agent_manager
            if "web_runtime" in inspect.signature(chat).parameters:
                chat_options["web_runtime"] = web_runtime
            chat(**chat_options)
    except RuntimeError as error:
        print(f"Error: {error}")
    finally:
        if "agent_manager" in locals():
            agent_manager.close()
        if "background_tasks" in locals():
            background_tasks.close()
        if "capability_runtime" in locals():
            capability_runtime.close()
        try:
            handle.close()
        except Exception as error:
            print(f"Persistence warning while closing session: {error}")
