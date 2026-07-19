"""Send one model request through OpenRouter."""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def required_environment(name: str) -> str:
    """Read one required setting and fail with a useful message if absent."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def generate(
    instructions: str,
    messages: list[Any],
    tools: list[dict[str, Any]],
) -> Any:
    """Send the current context to OpenRouter and return its raw response."""
    client = OpenAI(
        api_key=required_environment("OPENROUTER_API_KEY"),
        base_url=OPENROUTER_BASE_URL,
    )
    return client.responses.create(
        model=required_environment("OPENROUTER_MODEL"),
        instructions=instructions,
        input=messages,
        tools=tools,
    )
