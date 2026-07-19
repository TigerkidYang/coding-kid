"""The single model request used by the first version of Coding Kid."""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

DEFAULT_MODEL = "gpt-5.4-mini"


def generate(
    instructions: str,
    messages: list[Any],
    tools: list[dict[str, Any]],
) -> Any:
    """Send the current context to OpenAI and return its raw response."""
    client = OpenAI()
    return client.responses.create(
        model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        instructions=instructions,
        input=messages,
        tools=tools,
    )
