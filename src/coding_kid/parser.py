"""Turn the provider's raw response into data the agent loop can use."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """One tool call requested by the model."""

    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ParsedOutput:
    """The text and tool calls found in one model response."""

    text: str
    tool_calls: list[ToolCall]


def parse_output(response: Any) -> ParsedOutput:
    """Extract assistant text and function calls from a raw response."""
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    text_parts.append(content.text)
        elif item.type == "function_call":
            try:
                arguments = json.loads(item.arguments)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Tool {item.name!r} returned invalid JSON arguments"
                ) from error
            if not isinstance(arguments, dict):
                raise ValueError(f"Tool {item.name!r} arguments must be an object")
            tool_calls.append(ToolCall(item.call_id, item.name, arguments))

    return ParsedOutput("\n".join(text_parts), tool_calls)
