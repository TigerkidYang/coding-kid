"""Send one model request through OpenRouter."""

from __future__ import annotations

import os
import json
import urllib.error
import urllib.request
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
    *,
    max_output_tokens: int | None = None,
) -> Any:
    """Send the current context to OpenRouter and return its raw response."""
    client = OpenAI(
        api_key=required_environment("OPENROUTER_API_KEY"),
        base_url=OPENROUTER_BASE_URL,
        timeout=120.0,
        max_retries=2,
    )
    request: dict[str, Any] = {
        "model": required_environment("OPENROUTER_MODEL"),
        "instructions": instructions,
        "input": messages,
        "tools": tools,
    }
    if max_output_tokens is not None:
        request["max_output_tokens"] = max_output_tokens
    return client.responses.create(
        **request,
    )


def discover_context_length(model: str) -> int | None:
    """Return OpenRouter's context length for one exact model slug."""
    request = urllib.request.Request(
        f"{OPENROUTER_BASE_URL}/models",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            payload = json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return None
    for item in payload.get("data", []):
        if item.get("id") == model or item.get("canonical_slug") == model:
            context_length = item.get("context_length")
            if isinstance(context_length, int) and context_length > 0:
                return context_length
    return None


def response_input_tokens(response: Any) -> int | None:
    """Read Responses API input usage without requiring it in test doubles."""
    usage = getattr(response, "usage", None)
    value = getattr(usage, "input_tokens", None)
    return value if isinstance(value, int) and value >= 0 else None


def is_context_window_error(error: Exception) -> bool:
    """Recognize only explicit context-window failures."""
    status = getattr(error, "status_code", None)
    if status is not None and status not in {400, 413}:
        return False
    body = getattr(error, "body", None)
    rendered = f"{error} {body}".casefold()
    markers = (
        "context window",
        "context_length_exceeded",
        "maximum context length",
        "prompt is too long",
        "too many tokens",
    )
    return any(marker in rendered for marker in markers)
