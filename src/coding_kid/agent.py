"""The complete model -> tool -> model loop."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
import json
import time
from typing import Any, TYPE_CHECKING

from coding_kid.background_tasks import BackgroundTaskManager
from coding_kid.compaction import compact_context
from coding_kid.context import BASE_INSTRUCTIONS, SessionContext, build_instructions
from coding_kid.context_manager import (
    ContextBudget,
    ContextManager,
    ConversationState,
    estimate_request_tokens,
)
from coding_kid.events import (
    AssistantMessageCompleted,
    AssistantStreamReset,
    AssistantTextDelta,
    BudgetWarning,
    CancellationToken,
    ContextWarning,
    EventSink,
    RetryScheduled,
    StallDetected,
    TodoItem,
    TodoCompletionDeferred,
    TodoUpdated,
    StepStarted,
    ToolCompleted,
    ToolStarted,
    TransitionSelected,
    TurnCancelled,
    TurnCompleted,
    TurnFailed,
    TurnInterrupted,
    TurnStarted,
    emit,
)
from coding_kid.parser import parse_output
from coding_kid.permissions import PermissionBroker
from coding_kid.provider import (
    ProviderProtocolError,
    generate,
    is_context_window_error,
    is_null_collection_error,
    is_output_limit_error,
    provider_retry_delay,
    retryable_provider_error,
)
from coding_kid.tools import (
    DEFAULT_TOOL_REGISTRY,
    TodoState,
    ToolRegistry,
    clear_todos,
    dispatch_tool,
    get_todos,
    tool_definitions,
)
from coding_kid.turn_control import TransitionReason, TurnLimits
from coding_kid.workflow import WorkflowState
from coding_kid.workflow_runtime import WorkflowRuntime

if TYPE_CHECKING:
    from coding_kid.agents import AgentManager

SYSTEM_PROMPT = BASE_INSTRUCTIONS

EMPTY_RESPONSE_RECOVERY = """

Recovery instruction: The previous response was empty. Use the information and
tool results already available, and answer the user now. Do not return only
reasoning. Call another provided tool only if a specific missing fact requires it."""

TOOL_BUDGET_RECOVERY = """

Tool-call budget reached: Do not call any more file or shell tools in this turn.
Use the evidence already available and answer the user now. You may call todo
once to reconcile the checklist before answering."""

TODO_RECONCILIATION = """

Todo reconciliation suggestion: A checklist item is still in_progress. Choose
whether to continue, replace or defer the plan, or explain why work is stopping.
You may call todo once to reflect reality. You may also answer now; unfinished
items will remain visible and can be resumed later."""

OUTPUT_LIMIT_RECOVERY = """

Output limit recovery: The previous response was cut off. Resume directly from
the available work without apologizing or repeating the completed portion. Keep
the remainder concise and use tools only when necessary."""

STALL_RECOVERY = """

Stall circuit breaker: Repeated identical tool actions produced no new evidence.
Do not call more tools. Explain the useful evidence already collected and state
the remaining blocker clearly."""

Provider = Callable[..., Any]
StreamingProvider = Callable[..., Any]
ToolObserver = Callable[[str, dict[str, Any], str], None]
ContextObserver = Callable[[str], None]
MemoryCitationObserver = Callable[[tuple[str, ...]], None]
MAX_EMPTY_RESPONSES = 2
MAX_TOOL_CALLS_PER_TURN = 64
MAX_PROVIDER_ATTEMPTS = 3
MAX_OUTPUT_LIMIT_RECOVERIES = 2


class _RecoveryBoundary(RuntimeError):
    """Internal signal that converts a non-safety limit into a terminal result."""


def _provider_request_with_retry(
    request: Callable[[], Any],
    *,
    event_sink: EventSink | None,
    cancellation_token: CancellationToken | None,
) -> Any:
    """Run one observable, cancellable provider retry policy."""
    for attempt in range(1, MAX_PROVIDER_ATTEMPTS + 1):
        try:
            return request()
        except Exception as error:
            if not retryable_provider_error(error) or attempt >= MAX_PROVIDER_ATTEMPTS:
                raise
            delay = provider_retry_delay(error, attempt)
            emit(event_sink, AssistantStreamReset("provider_retry"))
            emit(event_sink, RetryScheduled(type(error).__name__, attempt, delay))
            emit(
                event_sink,
                TransitionSelected(TransitionReason.PROVIDER_RETRY.value),
            )
            if cancellation_token is None:
                time.sleep(delay)
            elif cancellation_token.wait(delay):
                cancellation_token.raise_if_cancelled()
    raise AssertionError("provider retry loop exhausted without returning")


def current_instructions(
    session_context: SessionContext | None = None,
    overlays: tuple[str, ...] = (),
    todo_state: TodoState | None = None,
) -> str:
    """Build stable runtime instructions plus current dynamic guidance."""
    context = session_context or SessionContext.capture()
    return build_instructions(
        context,
        todo_state.items if todo_state is not None else get_todos(),
        overlays,
        base_instructions=SYSTEM_PROMPT,
    )


def _manager_for_turn(
    conversation: list[Any] | ContextManager,
    session_context: SessionContext | None,
) -> tuple[ContextManager, list[Any] | None]:
    if isinstance(conversation, ContextManager):
        return conversation, None
    context = session_context or SessionContext.capture()
    manager = ContextManager(
        context,
        ContextBudget(None, "Version 03 compatibility input"),
        ConversationState.from_items(conversation),
    )
    return manager, conversation


def _run_turn_once(
    conversation: list[Any] | ContextManager,
    call_provider: Provider = generate,
    *,
    max_steps: int = 80,
    on_tool: ToolObserver | None = None,
    on_context: ContextObserver | None = None,
    session_context: SessionContext | None = None,
    stream_provider: StreamingProvider | None = None,
    event_sink: EventSink | None = None,
    cancellation_token: CancellationToken | None = None,
    request_context: list[Any] | None = None,
    on_memory_citations: MemoryCitationObserver | None = None,
    tool_registry: ToolRegistry | None = None,
    instruction_overlays: tuple[str, ...] = (),
    background_tasks: BackgroundTaskManager | None = None,
    todo_state: TodoState | None = None,
    max_tool_calls: int = MAX_TOOL_CALLS_PER_TURN,
    agent_manager: AgentManager | None = None,
    rollback_on_cancel: bool = False,
    limits: TurnLimits | None = None,
    permission_broker: PermissionBroker | None = None,
    workflow_state: WorkflowState | None = None,
    workflow_runtime: WorkflowRuntime | None = None,
) -> str:
    """Run model and tools until the model returns a final text response."""
    configured_limits = limits or TurnLimits(
        max_steps=max_steps,
        max_tool_calls=max_tool_calls,
    )
    max_steps = configured_limits.max_steps
    max_tool_calls = configured_limits.max_tool_calls
    registry = tool_registry or DEFAULT_TOOL_REGISTRY
    tools = registry.definitions() if tool_registry is not None else tool_definitions()
    dispatch = registry.dispatch if tool_registry is not None else dispatch_tool
    manager, compatibility_messages = _manager_for_turn(
        conversation,
        session_context,
    )
    context = manager.session_context
    turn_snapshot = manager.clone()
    empty_responses = 0
    todo_reconciliation_requested = False
    tool_calls_executed = 0
    recovery_overlays: tuple[str, ...] = ()
    reactive_recovery_attempted = False
    recovery_count = 0
    output_limit_recoveries = 0
    last_action_fingerprint: str | None = None
    identical_action_count = 0
    stalled = False
    budget_warned = False
    turn_started_at = time.monotonic()
    emit(event_sink, TurnStarted())

    def record_recovery(reason: TransitionReason) -> None:
        nonlocal recovery_count
        recovery_count += 1
        emit(event_sink, TransitionSelected(reason.value))
        if recovery_count > configured_limits.max_recoveries:
            raise _RecoveryBoundary("Turn recovery budget exhausted")

    try:
        for step_number in range(1, max_steps + 1):
            if (
                time.monotonic() - turn_started_at
                > configured_limits.max_elapsed_seconds
            ):
                emit(event_sink, BudgetWarning("Turn elapsed-time budget exhausted"))
                return _controlled_incomplete_result(
                    manager,
                    compatibility_messages,
                    event_sink,
                    "I stopped at the configured elapsed-time boundary. Completed "
                    "work and tool results were retained; the task may be resumed.",
                )
            emit(event_sink, StepStarted(step_number))
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()
            task_summary = (
                background_tasks.prompt_summary()
                if background_tasks is not None
                else ""
            )
            agent_summary = (
                agent_manager.prompt_summary() if agent_manager is not None else ""
            )
            task_overlay = tuple(
                summary for summary in (task_summary, agent_summary) if summary
            )
            workflow_overlay = (
                (workflow_state.instruction_text(),)
                if workflow_state is not None
                else ()
            )
            instructions = current_instructions(
                context,
                instruction_overlays
                + workflow_overlay
                + task_overlay
                + recovery_overlays,
                todo_state,
            )
            mode_tools = (
                registry.definitions_for_mode(workflow_state.mode)
                if workflow_state is not None
                else tools
            )
            active_tools = [] if stalled else mode_tools

            if manager.should_auto_compact(instructions, active_tools):
                try:
                    compact_context(
                        manager,
                        call_provider,
                        instructions=instructions,
                        tools=active_tools,
                        trigger="auto",
                        on_context=on_context,
                        event_sink=event_sink,
                        cancellation_token=cancellation_token,
                    )
                except (KeyboardInterrupt, TurnCancelled):
                    raise
                except Exception as error:  # noqa: BLE001
                    manager.record_auto_compaction_failure()
                    if on_context is not None:
                        on_context(
                            f"[context] warning: automatic compaction failed: {error}"
                        )
                    emit(
                        event_sink,
                        ContextWarning(f"Automatic compaction failed: {error}"),
                    )

            model_input = manager.model_input(request_context)
            local_estimate = estimate_request_tokens(
                instructions,
                model_input,
                active_tools,
            )
            try:

                def request() -> Any:
                    if stream_provider is None:
                        return call_provider(instructions, model_input, active_tools)
                    return stream_provider(
                        instructions,
                        model_input,
                        active_tools,
                        on_text_delta=lambda delta: emit(
                            event_sink, AssistantTextDelta(delta)
                        ),
                        cancellation_token=cancellation_token,
                    )

                response = _provider_request_with_retry(
                    request,
                    event_sink=event_sink,
                    cancellation_token=cancellation_token,
                )
                if cancellation_token is not None:
                    cancellation_token.raise_if_cancelled()
            except Exception as error:
                if (
                    is_context_window_error(error)
                    and not reactive_recovery_attempted
                    and manager.has_compactable_history()
                ):
                    compact_context(
                        manager,
                        call_provider,
                        instructions=instructions,
                        tools=active_tools,
                        trigger="recovery",
                        on_context=on_context,
                        event_sink=event_sink,
                        cancellation_token=cancellation_token,
                    )
                    record_recovery(TransitionReason.AUTO_COMPACTION)
                    reactive_recovery_attempted = True
                    continue
                if (
                    is_output_limit_error(error)
                    and output_limit_recoveries < MAX_OUTPUT_LIMIT_RECOVERIES
                ):
                    output_limit_recoveries += 1
                    record_recovery(TransitionReason.OUTPUT_LIMIT_RECOVERY)
                    recovery_overlays = (OUTPUT_LIMIT_RECOVERY,)
                    emit(event_sink, AssistantStreamReset("output_limit_recovery"))
                    continue
                raise

            manager.record_regular_response(response, local_estimate)
            parsed = parse_output(response)
            emit(
                event_sink,
                AssistantMessageCompleted(parsed.text, bool(parsed.tool_calls)),
            )
            round_items = _round_items(response, parsed.text, parsed.memory_citations)

            if stalled and parsed.tool_calls:
                round_items.extend(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": (
                            "Tool call skipped: the repeated-action circuit breaker "
                            "is active. Return a controlled incomplete result."
                        ),
                    }
                    for tool_call in parsed.tool_calls
                )
                manager.conversation.append_model_round(round_items)
                return _controlled_incomplete_result(
                    manager,
                    compatibility_messages,
                    event_sink,
                    "I stopped because repeated tool actions produced no new "
                    "evidence. Completed work and tool results were retained.",
                    reason=TransitionReason.STALLED,
                )

            if not parsed.tool_calls:
                manager.conversation.append_model_round(round_items)
                if parsed.text.strip():
                    todos = todo_state.items if todo_state is not None else get_todos()
                    has_in_progress = any(
                        item["status"] == "in_progress" for item in todos
                    )
                    if has_in_progress and not todo_reconciliation_requested:
                        todo_reconciliation_requested = True
                        emit(
                            event_sink,
                            TransitionSelected(TransitionReason.COMPLETION_RETRY.value),
                        )
                        recovery_overlays = (TODO_RECONCILIATION,)
                        if tool_calls_executed >= max_tool_calls:
                            recovery_overlays += (TOOL_BUDGET_RECOVERY,)
                        continue
                    incomplete = tuple(
                        TodoItem(item["content"], item["status"])
                        for item in todos
                        if item["status"] != "completed"
                    )
                    if incomplete:
                        emit(
                            event_sink,
                            TodoCompletionDeferred(
                                incomplete,
                                reminder_sent=todo_reconciliation_requested,
                            ),
                        )
                    if todos and all(item["status"] == "completed" for item in todos):
                        if todo_state is None:
                            clear_todos()
                        else:
                            todo_state.clear()
                    if compatibility_messages is not None:
                        compatibility_messages[:] = manager.conversation.active_items()
                    if on_memory_citations is not None:
                        try:
                            on_memory_citations(parsed.memory_citations)
                        except Exception as error:  # noqa: BLE001
                            emit(
                                event_sink,
                                ContextWarning(
                                    f"Memory usage tracking failed: {error}"
                                ),
                            )
                    emit(
                        event_sink,
                        TransitionSelected(TransitionReason.COMPLETED.value),
                    )
                    emit(event_sink, TurnCompleted(parsed.text))
                    return parsed.text

                empty_responses += 1
                if empty_responses >= MAX_EMPTY_RESPONSES:
                    return _controlled_incomplete_result(
                        manager,
                        compatibility_messages,
                        event_sink,
                        "The model returned repeated empty responses. Completed "
                        "work and tool results were retained.",
                        reason=TransitionReason.EMPTY_RESPONSE_RECOVERY,
                    )
                recovery_overlays = (EMPTY_RESPONSE_RECOVERY,)
                record_recovery(TransitionReason.EMPTY_RESPONSE_RECOVERY)
                if tool_calls_executed >= max_tool_calls:
                    recovery_overlays += (TOOL_BUDGET_RECOVERY,)
                continue

            empty_responses = 0
            tool_budget_reached = tool_calls_executed >= max_tool_calls

            tool_results: list[str | None] = [None] * len(parsed.tool_calls)
            for tool_index, tool_call in enumerate(parsed.tool_calls):
                if cancellation_token is not None:
                    cancellation_token.raise_if_cancelled()
                if tool_calls_executed >= max_tool_calls and tool_call.name not in {
                    "todo",
                    "skill",
                }:
                    result = (
                        "Tool call skipped: the per-turn tool-call budget was reached. "
                        "Use the results already available and answer the user."
                    )
                    tool_budget_reached = True
                    if not budget_warned:
                        emit(event_sink, BudgetWarning("Tool-call budget reached"))
                        budget_warned = True
                    tool_results[tool_index] = result
                else:
                    if tool_call.name not in {"todo", "skill"}:
                        tool_calls_executed += 1
                    if tool_calls_executed >= max_tool_calls:
                        tool_budget_reached = True

            def invoke_tool(tool_index: int) -> str:
                tool_call = parsed.tool_calls[tool_index]
                effect = registry.effect(tool_call.name, tool_call.arguments)
                if permission_broker is not None:
                    authorization = registry.authorize(
                        tool_call.name,
                        tool_call.arguments,
                        permission_broker,
                        cancellation_token=cancellation_token,
                        event_sink=event_sink,
                    )
                    if not authorization.allowed:
                        result = f"ERROR: {authorization.message}"
                        emit(
                            event_sink,
                            ToolCompleted(
                                tool_call.name,
                                dict(tool_call.arguments),
                                result,
                            ),
                        )
                        return result
                if workflow_runtime is not None:
                    try:
                        recovery_warning = workflow_runtime.before_effect(
                            effect,
                            tool_name=tool_call.name,
                            recovery_paths=registry.recovery_paths(
                                tool_call.name, tool_call.arguments
                            ),
                        )
                    except Exception as error:  # noqa: BLE001
                        result = f"ERROR: {type(error).__name__}: {error}"
                        emit(
                            event_sink,
                            ToolCompleted(
                                tool_call.name,
                                dict(tool_call.arguments),
                                result,
                            ),
                        )
                        return result
                    if recovery_warning:
                        emit(event_sink, ContextWarning(recovery_warning))
                emit(
                    event_sink,
                    ToolStarted(tool_call.name, dict(tool_call.arguments)),
                )
                result = dispatch(tool_call.name, tool_call.arguments)
                if workflow_runtime is not None:
                    try:
                        workflow_runtime.after_effect(effect)
                    except Exception as error:  # noqa: BLE001
                        result = (
                            f"{result}\nERROR: Change tracking failed after the tool: "
                            f"{type(error).__name__}: {error}"
                        )
                if on_tool is not None:
                    on_tool(tool_call.name, tool_call.arguments, result)
                emit(
                    event_sink,
                    ToolCompleted(
                        tool_call.name,
                        dict(tool_call.arguments),
                        result,
                    ),
                )
                if tool_call.name == "todo" and not result.startswith("ERROR:"):
                    emit(
                        event_sink,
                        TodoUpdated(
                            tuple(
                                TodoItem(item["content"], item["status"])
                                for item in (
                                    todo_state.items
                                    if todo_state is not None
                                    else get_todos()
                                )
                            )
                        ),
                    )
                return result

            tool_index = 0
            while tool_index < len(parsed.tool_calls):
                if tool_results[tool_index] is not None:
                    tool_index += 1
                    continue
                if registry.parallel_safe(parsed.tool_calls[tool_index].name):
                    batch: list[int] = []
                    while (
                        tool_index < len(parsed.tool_calls)
                        and tool_results[tool_index] is None
                        and registry.parallel_safe(parsed.tool_calls[tool_index].name)
                    ):
                        batch.append(tool_index)
                        tool_index += 1
                    with ThreadPoolExecutor(
                        max_workers=min(4, len(batch)),
                        thread_name_prefix="coding-kid-read",
                    ) as executor:
                        futures = [
                            executor.submit(invoke_tool, index) for index in batch
                        ]
                        for index, future in zip(batch, futures, strict=True):
                            tool_results[index] = future.result()
                else:
                    tool_results[tool_index] = invoke_tool(tool_index)
                    tool_index += 1

                if cancellation_token is not None and cancellation_token.cancelled:
                    for pending_index, pending_result in enumerate(tool_results):
                        if pending_result is None:
                            tool_results[pending_index] = (
                                "Tool call skipped: turn cancelled."
                            )
                    round_items.extend(
                        {
                            "type": "function_call_output",
                            "call_id": tool_call.call_id,
                            "output": result,
                        }
                        for tool_call, result in zip(
                            parsed.tool_calls, tool_results, strict=True
                        )
                    )
                    manager.conversation.append_model_round(round_items)
                    cancellation_token.raise_if_cancelled()

            for tool_call, result in zip(parsed.tool_calls, tool_results, strict=True):
                assert result is not None
                fingerprint = json.dumps(
                    [tool_call.name, tool_call.arguments, result],
                    sort_keys=True,
                    ensure_ascii=False,
                    default=str,
                )
                if fingerprint == last_action_fingerprint:
                    identical_action_count += 1
                else:
                    last_action_fingerprint = fingerprint
                    identical_action_count = 1
                if identical_action_count == 3:
                    emit(
                        event_sink,
                        StallDetected(
                            f"Repeated {tool_call.name} with the same result three times"
                        ),
                    )
                if identical_action_count >= configured_limits.max_identical_actions:
                    stalled = True
                round_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": result,
                    }
                )

            manager.conversation.append_model_round(round_items)
            if (
                workflow_runtime is not None
                and workflow_runtime.consume_clear_context()
            ):
                approved_plan = workflow_runtime.state.approved_plan or ""
                manager.conversation.reset_active_to_user(
                    "Implement the approved plan below in a fresh context.\n\n"
                    f"{approved_plan}"
                )
            emit(
                event_sink,
                TransitionSelected(TransitionReason.TOOL_FOLLOWUP.value),
            )
            if stalled:
                emit(
                    event_sink,
                    TransitionSelected(TransitionReason.STALLED.value),
                )
                recovery_overlays = (STALL_RECOVERY,)
            else:
                recovery_overlays = (
                    (TOOL_BUDGET_RECOVERY,) if tool_budget_reached else ()
                )

        emit(event_sink, BudgetWarning("Model/tool step boundary reached"))
        return _controlled_incomplete_result(
            manager,
            compatibility_messages,
            event_sink,
            "I stopped at the configured model/tool step boundary. Completed "
            "work and tool results were retained; the task may be resumed.",
        )
    except _RecoveryBoundary as error:
        return _controlled_incomplete_result(
            manager,
            compatibility_messages,
            event_sink,
            f"{error}. Completed work and tool results were retained; the task "
            "may be resumed.",
        )
    except TurnCancelled as error:
        if rollback_on_cancel:
            manager.restore(turn_snapshot)
        else:
            manager.conversation.restore_projection_preserving_new_transcript(
                turn_snapshot.conversation
            )
        emit(
            event_sink,
            TransitionSelected(
                TransitionReason.USER_STEER.value
                if error.reason == "steered"
                else TransitionReason.INTERRUPTED.value
            ),
        )
        emit(event_sink, TurnInterrupted(str(error)))
        raise
    except BaseException as error:
        manager.conversation.restore_projection_preserving_new_transcript(
            turn_snapshot.conversation
        )
        if isinstance(error, ProviderProtocolError):
            raise
        if is_null_collection_error(error):
            raise ProviderProtocolError(
                "Provider returned a null collection while processing a model round"
            ) from error
        emit(
            event_sink,
            TransitionSelected(TransitionReason.FATAL_ERROR.value),
        )
        emit(event_sink, TurnFailed(str(error)))
        raise


def run_turn(
    conversation: list[Any] | ContextManager,
    call_provider: Provider = generate,
    *,
    max_steps: int = 80,
    on_tool: ToolObserver | None = None,
    on_context: ContextObserver | None = None,
    session_context: SessionContext | None = None,
    stream_provider: StreamingProvider | None = None,
    event_sink: EventSink | None = None,
    cancellation_token: CancellationToken | None = None,
    request_context: list[Any] | None = None,
    on_memory_citations: MemoryCitationObserver | None = None,
    tool_registry: ToolRegistry | None = None,
    instruction_overlays: tuple[str, ...] = (),
    background_tasks: BackgroundTaskManager | None = None,
    todo_state: TodoState | None = None,
    max_tool_calls: int = MAX_TOOL_CALLS_PER_TURN,
    agent_manager: AgentManager | None = None,
    rollback_on_cancel: bool = False,
    limits: TurnLimits | None = None,
    permission_broker: PermissionBroker | None = None,
    workflow_state: WorkflowState | None = None,
    workflow_runtime: WorkflowRuntime | None = None,
) -> str:
    """Run one turn, resuming once after a null-collection protocol failure."""
    turn_conversation: list[Any] | ContextManager = conversation
    compatibility_messages: list[Any] | None = None
    compatibility_manager: ContextManager | None = None
    if isinstance(conversation, list):
        manager, compatibility_messages = _manager_for_turn(
            conversation, session_context
        )
        turn_conversation = manager
        compatibility_manager = manager
    options = {
        "max_steps": max_steps,
        "on_tool": on_tool,
        "on_context": on_context,
        "session_context": session_context,
        "stream_provider": stream_provider,
        "event_sink": event_sink,
        "cancellation_token": cancellation_token,
        "request_context": request_context,
        "on_memory_citations": on_memory_citations,
        "tool_registry": tool_registry,
        "instruction_overlays": instruction_overlays,
        "background_tasks": background_tasks,
        "todo_state": todo_state,
        "max_tool_calls": max_tool_calls,
        "agent_manager": agent_manager,
        "rollback_on_cancel": rollback_on_cancel,
        "limits": limits,
        "permission_broker": permission_broker,
        "workflow_state": workflow_state,
        "workflow_runtime": workflow_runtime,
    }
    for attempt in range(1, 3):
        try:
            result = _run_turn_once(turn_conversation, call_provider, **options)
            if compatibility_messages is not None and compatibility_manager is not None:
                compatibility_messages[:] = (
                    compatibility_manager.conversation.active_items()
                )
            return result
        except ProviderProtocolError:
            if attempt >= 2:
                raise
            delay = 0.5
            emit(event_sink, AssistantStreamReset("model_round_protocol_retry"))
            emit(event_sink, RetryScheduled("ProviderProtocolError", attempt, delay))
            emit(event_sink, TransitionSelected(TransitionReason.PROVIDER_RETRY.value))
            if cancellation_token is None:
                time.sleep(delay)
            elif cancellation_token.wait(delay):
                cancellation_token.raise_if_cancelled()
    raise AssertionError("model-round retry loop exhausted without returning")


def _round_items(
    response: Any,
    visible_text: str,
    memory_citations: tuple[str, ...],
) -> list[Any]:
    """Remove a valid machine-only citation footer from committed history."""
    items = list(getattr(response, "output", None) or ())
    if not memory_citations:
        return items
    normalized: list[Any] = []
    replaced = False
    for item in items:
        if not replaced and getattr(item, "type", None) == "message":
            normalized.append(
                {
                    "type": "message",
                    "role": getattr(item, "role", "assistant"),
                    "content": [{"type": "output_text", "text": visible_text}],
                }
            )
            replaced = True
        else:
            normalized.append(item)
    return normalized


def _controlled_incomplete_result(
    manager: ContextManager,
    compatibility_messages: list[Any] | None,
    event_sink: EventSink | None,
    message: str,
    *,
    reason: TransitionReason = TransitionReason.BUDGET_EXHAUSTED,
) -> str:
    """Commit a model-visible terminal result without treating a limit as fatal."""
    manager.conversation.append_model_round(
        [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": message}],
            }
        ]
    )
    if compatibility_messages is not None:
        compatibility_messages[:] = manager.conversation.active_items()
    emit(event_sink, TransitionSelected(reason.value))
    emit(event_sink, TurnCompleted(message))
    return message
