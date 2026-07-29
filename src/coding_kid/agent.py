"""The complete model -> tool -> model loop."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from coding_kid.context import (
    BASE_INSTRUCTIONS,
    SessionContext,
    build_instructions,
    build_model_input,
)
from coding_kid.parser import parse_output
from coding_kid.provider import generate
from coding_kid.tools import (
    clear_todos,
    dispatch_tool,
    get_todos,
    tool_definitions,
)

# Kept as a named compatibility point for tests and evaluation adapters.
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

Provider = Callable[[str, list[Any], list[dict[str, Any]]], Any]
ToolObserver = Callable[[str, dict[str, Any], str], None]
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


def run_turn(
    messages: list[Any],
    call_provider: Provider = generate,
    *,
    max_steps: int = 80,
    on_tool: ToolObserver | None = None,
    session_context: SessionContext | None = None,
) -> str:
    """Run model and tools until the model returns a final text response."""
    tools = tool_definitions()
    working_messages = list(messages)
    context = session_context or SessionContext.capture()
    empty_responses = 0
    todo_reconciliation_requested = False
    tool_calls_executed = 0
    instruction_overlays: tuple[str, ...] = ()

    for _ in range(max_steps):
        instructions = current_instructions(context, instruction_overlays)
        model_input = build_model_input(context, working_messages)
        response = call_provider(instructions, model_input, tools)

        # Parse before changing history so malformed provider output cannot
        # leave an incomplete turn behind.
        parsed = parse_output(response)

        # Keeping the raw output items preserves exactly what the model said and
        # requested when the complete history is sent on the next step.
        working_messages.extend(response.output)
        if not parsed.tool_calls:
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
                messages[:] = working_messages
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

        # Multiple calls are deliberately sequential in this first version.
        for tool_call in parsed.tool_calls:
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
                result = dispatch_tool(tool_call.name, tool_call.arguments)
                # Todo updates are planning overhead and do not consume the
                # per-turn file/shell tool budget.
                if tool_call.name != "todo":
                    tool_calls_executed += 1
                if on_tool is not None:
                    on_tool(tool_call.name, tool_call.arguments, result)
                if tool_calls_executed >= MAX_TOOL_CALLS_PER_TURN:
                    tool_budget_reached = True
            working_messages.append(
                {
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": result,
                }
            )

        instruction_overlays = (TOOL_BUDGET_RECOVERY,) if tool_budget_reached else ()

    raise RuntimeError("Agent reached the maximum number of model/tool steps")
