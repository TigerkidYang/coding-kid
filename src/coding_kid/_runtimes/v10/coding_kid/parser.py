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

    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    text_parts.append(content.text)
        elif item.type == "function_call":
            try:
                arguments = json.loads(item.arguments)
            except (json.JSONDecodeError, TypeError) as error:
                raise ValueError(
                    f"Tool {item.name!r} returned invalid JSON arguments"
                ) from error
            if not isinstance(arguments, dict):
                raise ValueError(f"Tool {item.name!r} arguments must be an object")
            tool_calls.append(ToolCall(item.call_id, item.name, arguments))

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
