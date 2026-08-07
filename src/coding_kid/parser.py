"""Turn the provider's raw response into data the agent loop can use."""

from __future__ import annotations

import json
import re
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
    memory_citations: tuple[str, ...] = ()


_MEMORY_CITATIONS = re.compile(
    r"\s*<coding_kid_memory_citations>(.*?)</coding_kid_memory_citations>\s*$",
    re.DOTALL,
)


def parse_output(response: Any) -> ParsedOutput:
    """Extract assistant text and function calls from a raw response."""
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    for item in getattr(response, "output", None) or ():
        item_type = getattr(item, "type", None)
        if item_type == "message":
            for content in getattr(item, "content", None) or ():
                if getattr(content, "type", None) == "output_text":
                    text = getattr(content, "text", "")
                    if isinstance(text, str):
                        text_parts.append(text)
        elif item_type == "function_call":
            try:
                arguments = json.loads(getattr(item, "arguments", None))
            except (json.JSONDecodeError, TypeError) as error:
                raise ValueError(
                    f"Tool {getattr(item, 'name', None)!r} returned invalid JSON arguments"
                ) from error
            if not isinstance(arguments, dict):
                raise ValueError(
                    f"Tool {getattr(item, 'name', None)!r} arguments must be an object"
                )
            call_id = getattr(item, "call_id", None)
            name = getattr(item, "name", None)
            if not isinstance(call_id, str) or not isinstance(name, str):
                raise ValueError("Tool call is missing a string call_id or name")
            tool_calls.append(ToolCall(call_id, name, arguments))

    text = "\n".join(text_parts)
    if not text:
        aggregate_text = getattr(response, "output_text", "")
        if isinstance(aggregate_text, str):
            text = aggregate_text

    citations: tuple[str, ...] = ()
    match = _MEMORY_CITATIONS.search(text)
    if match is not None:
        try:
            candidate = json.loads(match.group(1))
        except json.JSONDecodeError:
            candidate = None
        if isinstance(candidate, list) and all(
            isinstance(item, str) for item in candidate
        ):
            citations = tuple(dict.fromkeys(candidate))
            text = text[: match.start()].rstrip()

    return ParsedOutput(text, tool_calls, citations)
