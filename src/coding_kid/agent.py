"""The complete model -> tool -> model loop."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from coding_kid.parser import parse_output
from coding_kid.provider import generate
from coding_kid.tools import (
    clear_todos,
    dispatch_tool,
    format_todos,
    get_todos,
    tool_definitions,
)

SYSTEM_PROMPT = f"""You are Coding Kid, a coding agent working in the current directory.
Only call the tools provided in the current request. Never invent tool names.
Use the available tools to inspect, change, and verify code when needed.
Read or search before changing code you have not inspected.
Use "." for the current directory; never send an empty path or search query.
Use the fewest tool calls needed and stop gathering once you can answer.
For repository overviews, inspect only the top level, README, project configuration,
one relevant architecture/context document, and source/test file names. Do not read
every file, run tests, inspect Git state or diffs, inspect version archives, run
recursive tree commands, or inspect virtual environments, caches, or dependencies
unless the user specifically asks.
For tasks with three or more distinct steps, use the todo tool to list the steps
before making changes. Keep at most one item in_progress. Update the list as you
finish each step. Treat the checklist as an execution schedule: keep initial
inspection bounded, move to implementation as soon as the relevant code is
understood, and reserve tool calls for verification. For coding tasks that use
todo, spend no more than the first 6 file or shell calls on initial inspection
and reserve at least 2 calls for focused verification. Do not spend the whole
turn investigating while implementation or verification remains pending.
Skip the todo tool for simple one-step requests.
After using tools, always answer the user with the useful result. Never finish
with only internal reasoning or an empty response.
When the task is complete, explain the result clearly and briefly.
Current working directory: {Path.cwd()}
Configured model (OPENROUTER_MODEL): {os.getenv("OPENROUTER_MODEL", "not set")}
The execute tool runs commands through Windows cmd.exe. Use Windows commands."""

EMPTY_RESPONSE_RECOVERY = """

Recovery instruction: The previous response was empty. Use the information and
tool results already available, and answer the user now. Do not return only
reasoning. Call another provided tool only if a specific missing fact requires it."""

TOOL_BUDGET_RECOVERY = """

Tool-call budget reached: Do not call any more file or shell tools in this turn.
Use the evidence already available and answer the user now. You may call todo
once to reconcile the checklist before answering."""

TODO_RECONCILIATION = """

Todo reconciliation required: A checklist item is still in_progress. Before
answering, call todo once to reflect the actual state. Mark finished work
completed; if work must continue later, move the active item back to pending.
Then answer the user honestly about what is complete and what remains."""

Provider = Callable[[str, list[Any], list[dict[str, Any]]], Any]
ToolObserver = Callable[[str, dict[str, Any], str], None]
MAX_EMPTY_RESPONSES = 2
MAX_TOOL_CALLS_PER_TURN = 12
MAX_TOOL_CALLS_PER_TODO_STEP = 6


def current_instructions() -> str:
    """Build the system instructions, including the active todo list when set."""
    todos = get_todos()
    if not todos:
        return SYSTEM_PROMPT
    return f"{SYSTEM_PROMPT}\n\nCurrent todos:\n{format_todos(todos)}"


def run_turn(
    messages: list[Any],
    call_provider: Provider = generate,
    *,
    max_steps: int = 20,
    on_tool: ToolObserver | None = None,
) -> str:
    """Run model and tools until the model returns a final text response."""
    tools = tool_definitions()
    working_messages = list(messages)
    empty_responses = 0
    todo_reconciliation_requested = False
    tool_calls_executed = 0
    todo_step_calls = 0
    todo_schedule: tuple[tuple[str, str], ...] = ()
    instructions = current_instructions()

    for _ in range(max_steps):
        response = call_provider(instructions, working_messages, tools)

        # Parse before changing history so malformed provider output cannot
        # leave an incomplete turn behind.
        parsed = parse_output(response)

        # Keeping the raw output items preserves exactly what the model said and
        # requested when the complete history is sent on the next step.
        working_messages.extend(response.output)
        if not parsed.tool_calls:
            if parsed.text.strip():
                todos = get_todos()
                has_active_todo = any(item["status"] == "in_progress" for item in todos)
                if has_active_todo and not todo_reconciliation_requested:
                    todo_reconciliation_requested = True
                    instructions = f"{current_instructions()}{TODO_RECONCILIATION}"
                    if tool_calls_executed >= MAX_TOOL_CALLS_PER_TURN:
                        instructions = f"{instructions}{TOOL_BUDGET_RECOVERY}"
                    continue
                if has_active_todo:
                    raise RuntimeError(
                        "Model returned a final answer with a todo still in_progress"
                    )
                if todos and all(item["status"] == "completed" for item in todos):
                    clear_todos()
                messages[:] = working_messages
                return parsed.text

            empty_responses += 1
            if empty_responses >= MAX_EMPTY_RESPONSES:
                raise RuntimeError("Model returned repeated empty responses")
            instructions = f"{current_instructions()}{EMPTY_RESPONSE_RECOVERY}"
            if tool_calls_executed >= MAX_TOOL_CALLS_PER_TURN:
                instructions = f"{instructions}{TOOL_BUDGET_RECOVERY}"
            continue

        empty_responses = 0
        tool_budget_reached = tool_calls_executed >= MAX_TOOL_CALLS_PER_TURN

        # Multiple calls are deliberately sequential in this first version.
        for tool_call in parsed.tool_calls:
            schedule_blocked = (
                tool_call.name != "todo"
                and bool(get_todos())
                and todo_step_calls >= MAX_TOOL_CALLS_PER_TODO_STEP
            )
            if schedule_blocked:
                result = (
                    "Tool call paused: this todo step used its scheduled tool-call "
                    "allocation. Update todo to record the step's actual result and "
                    "activate the next step before using more file or shell tools."
                )
            elif (
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
                if tool_call.name == "todo" and not result.startswith("ERROR:"):
                    new_schedule = tuple(
                        (item["content"].strip(), item["status"])
                        for item in tool_call.arguments["todos"]
                    )
                    if new_schedule != todo_schedule:
                        todo_schedule = new_schedule
                        todo_step_calls = 0
                elif tool_call.name != "todo":
                    tool_calls_executed += 1
                    todo_step_calls += 1
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

        instructions = current_instructions()
        if tool_budget_reached:
            instructions = f"{instructions}{TOOL_BUDGET_RECOVERY}"

    raise RuntimeError("Agent reached the maximum number of model/tool steps")
