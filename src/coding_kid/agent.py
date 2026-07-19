"""The complete model -> tool -> model loop."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from coding_kid.parser import parse_output
from coding_kid.provider import generate
from coding_kid.tools import dispatch_tool, tool_definitions

SYSTEM_PROMPT = f"""You are Coding Kid, a coding agent working in the current directory.
Use the available tools to inspect, change, and verify code when needed.
Read or search before changing code you have not inspected.
When the task is complete, explain the result clearly and briefly.
Current working directory: {Path.cwd()}
Configured model (OPENROUTER_MODEL): {os.getenv("OPENROUTER_MODEL", "not set")}
The execute tool runs commands through Windows cmd.exe. Use Windows commands."""

Provider = Callable[[str, list[Any], list[dict[str, Any]]], Any]
ToolObserver = Callable[[str, dict[str, Any], str], None]


def run_turn(
    messages: list[Any],
    call_provider: Provider = generate,
    *,
    max_steps: int = 20,
    on_tool: ToolObserver | None = None,
) -> str:
    """Run model and tools until the model returns a final text response."""
    tools = tool_definitions()

    for _ in range(max_steps):
        response = call_provider(SYSTEM_PROMPT, messages, tools)

        # Keeping the raw output items preserves exactly what the model said and
        # requested when the complete history is sent on the next step.
        messages.extend(response.output)
        parsed = parse_output(response)
        if not parsed.tool_calls:
            return parsed.text

        # Multiple calls are deliberately sequential in this first version.
        for tool_call in parsed.tool_calls:
            result = dispatch_tool(tool_call.name, tool_call.arguments)
            if on_tool is not None:
                on_tool(tool_call.name, tool_call.arguments, result)
            messages.append(
                {
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": result,
                }
            )

    raise RuntimeError("Agent reached the maximum number of model/tool steps")
