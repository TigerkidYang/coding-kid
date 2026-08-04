"""The complete model -> tool -> model loop."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

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
    AssistantTextDelta,
    CancellationToken,
    ContextWarning,
    EventSink,
    TodoItem,
    TodoUpdated,
    ToolCompleted,
    ToolStarted,
    TurnCancelled,
    TurnCompleted,
    TurnFailed,
    TurnInterrupted,
    TurnStarted,
    emit,
)
from coding_kid.parser import parse_output
from coding_kid.provider import generate, is_context_window_error
from coding_kid.tools import (
    clear_todos,
    dispatch_tool,
    get_todos,
    tool_definitions,
)

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

Todo reconciliation required: One or more checklist items are incomplete.
Before answering, call todo once to reflect the actual state and finish the
remaining work. Do not give a final answer while any item is pending or
in_progress."""

Provider = Callable[..., Any]
StreamingProvider = Callable[..., Any]
ToolObserver = Callable[[str, dict[str, Any], str], None]
ContextObserver = Callable[[str], None]
MemoryCitationObserver = Callable[[tuple[str, ...]], None]
MAX_EMPTY_RESPONSES = 2
MAX_TOOL_CALLS_PER_TURN = 64


def current_instructions(
    session_context: SessionContext | None = None,
    overlays: tuple[str, ...] = (),
) -> str:
    """Build stable runtime instructions plus current dynamic guidance."""
    context = session_context or SessionContext.capture()
    return build_instructions(
        context,
        get_todos(),
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
) -> str:
    """Run model and tools until the model returns a final text response."""
    tools = tool_definitions()
    manager, compatibility_messages = _manager_for_turn(
        conversation,
        session_context,
    )
    context = manager.session_context
    turn_snapshot = manager.clone()
    empty_responses = 0
    todo_reconciliation_requested = False
    tool_calls_executed = 0
    instruction_overlays: tuple[str, ...] = ()
    reactive_recovery_attempted = False
    emit(event_sink, TurnStarted())

    try:
        for _ in range(max_steps):
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()
            instructions = current_instructions(context, instruction_overlays)

            if manager.should_auto_compact(instructions, tools):
                try:
                    compact_context(
                        manager,
                        call_provider,
                        instructions=instructions,
                        tools=tools,
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
                tools,
            )
            try:
                if stream_provider is None:
                    response = call_provider(instructions, model_input, tools)
                else:
                    response = stream_provider(
                        instructions,
                        model_input,
                        tools,
                        on_text_delta=lambda delta: emit(
                            event_sink, AssistantTextDelta(delta)
                        ),
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
                        tools=tools,
                        trigger="recovery",
                        on_context=on_context,
                        event_sink=event_sink,
                        cancellation_token=cancellation_token,
                    )
                    reactive_recovery_attempted = True
                    continue
                raise

            manager.record_regular_response(response, local_estimate)
            parsed = parse_output(response)
            emit(
                event_sink,
                AssistantMessageCompleted(parsed.text, bool(parsed.tool_calls)),
            )
            round_items = _round_items(response, parsed.text, parsed.memory_citations)

            if not parsed.tool_calls:
                manager.conversation.append_model_round(round_items)
                if parsed.text.strip():
                    todos = get_todos()
                    has_incomplete_todo = any(
                        item["status"] != "completed" for item in todos
                    )
                    if has_incomplete_todo and not todo_reconciliation_requested:
                        todo_reconciliation_requested = True
                        instruction_overlays = (TODO_RECONCILIATION,)
                        if tool_calls_executed >= MAX_TOOL_CALLS_PER_TURN:
                            instruction_overlays += (TOOL_BUDGET_RECOVERY,)
                        continue
                    if has_incomplete_todo:
                        raise RuntimeError(
                            "Model returned a final answer with unfinished todos"
                        )
                    if todos and all(item["status"] == "completed" for item in todos):
                        clear_todos()
                    if compatibility_messages is not None:
                        compatibility_messages[:] = manager.conversation.active_items()
                    if on_memory_citations is not None:
                        on_memory_citations(parsed.memory_citations)
                    emit(event_sink, TurnCompleted(parsed.text))
                    return parsed.text

                empty_responses += 1
                if empty_responses >= MAX_EMPTY_RESPONSES:
                    raise RuntimeError("Model returned repeated empty responses")
                instruction_overlays = (EMPTY_RESPONSE_RECOVERY,)
                if tool_calls_executed >= MAX_TOOL_CALLS_PER_TURN:
                    instruction_overlays += (TOOL_BUDGET_RECOVERY,)
                continue

            empty_responses = 0
            tool_budget_reached = tool_calls_executed >= MAX_TOOL_CALLS_PER_TURN

            for tool_call in parsed.tool_calls:
                if cancellation_token is not None:
                    cancellation_token.raise_if_cancelled()
                if (
                    tool_calls_executed >= MAX_TOOL_CALLS_PER_TURN
                    and tool_call.name != "todo"
                ):
                    result = (
                        "Tool call skipped: the per-turn tool-call budget was reached. "
                        "Use the results already available and answer the user."
                    )
                    tool_budget_reached = True
                else:
                    emit(
                        event_sink,
                        ToolStarted(tool_call.name, dict(tool_call.arguments)),
                    )
                    result = dispatch_tool(tool_call.name, tool_call.arguments)
                    if tool_call.name != "todo":
                        tool_calls_executed += 1
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
                                    for item in get_todos()
                                )
                            ),
                        )
                    if cancellation_token is not None:
                        cancellation_token.raise_if_cancelled()
                    if tool_calls_executed >= MAX_TOOL_CALLS_PER_TURN:
                        tool_budget_reached = True
                round_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": result,
                    }
                )

            manager.conversation.append_model_round(round_items)
            instruction_overlays = (
                (TOOL_BUDGET_RECOVERY,) if tool_budget_reached else ()
            )

        raise RuntimeError("Agent reached the maximum number of model/tool steps")
    except TurnCancelled as error:
        manager.restore(turn_snapshot)
        emit(event_sink, TurnInterrupted(str(error)))
        raise
    except BaseException as error:
        manager.restore(turn_snapshot)
        emit(event_sink, TurnFailed(str(error)))
        raise


def _round_items(
    response: Any,
    visible_text: str,
    memory_citations: tuple[str, ...],
) -> list[Any]:
    """Remove a valid machine-only citation footer from committed history."""
    items = list(response.output)
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
