"""Send one model request through OpenRouter."""

from __future__ import annotations

import os
import json
import urllib.error
import urllib.request
from typing import Any, Callable

from openai import OpenAI

from coding_kid.events import CancellationToken

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class ProviderIncompleteError(RuntimeError):
    """A streaming response ended intentionally before a complete response."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Streaming response incomplete: {reason}")
        self.reason = reason


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
        max_retries=0,
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


def generate_streaming(
    instructions: str,
    messages: list[Any],
    tools: list[dict[str, Any]],
    *,
    on_text_delta: Callable[[str], None],
    cancellation_token: CancellationToken | None = None,
    max_output_tokens: int | None = None,
) -> Any:
    """Stream visible text while retaining one complete provider response."""
    client = OpenAI(
        api_key=required_environment("OPENROUTER_API_KEY"),
        base_url=OPENROUTER_BASE_URL,
        timeout=120.0,
        max_retries=0,
    )
    request: dict[str, Any] = {
        "model": required_environment("OPENROUTER_MODEL"),
        "instructions": instructions,
        "input": messages,
        "tools": tools,
        "stream": True,
    }
    if max_output_tokens is not None:
        request["max_output_tokens"] = max_output_tokens

    stream = client.responses.create(**request)
    final_response: Any | None = None
    try:
        for event in stream:
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()
            event_type = getattr(event, "type", "")
            if event_type in {
                "response.output_text.delta",
                "response.content_part.delta",
            }:
                delta = getattr(event, "delta", None)
                if isinstance(delta, str) and delta:
                    on_text_delta(delta)
            elif event_type in {"response.completed", "response.done"}:
                final_response = getattr(event, "response", None)
            elif event_type == "response.incomplete":
                response = getattr(event, "response", None)
                details = getattr(response, "incomplete_details", None)
                reason = getattr(details, "reason", None) or "unknown"
                raise ProviderIncompleteError(str(reason))
            elif event_type in {"response.error", "response.failed"}:
                raise RuntimeError(_stream_error_message(event))
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()

    if cancellation_token is not None:
        cancellation_token.raise_if_cancelled()
    if final_response is None:
        raise RuntimeError("Streaming response ended without a terminal response")
    return final_response


def _stream_error_message(event: Any) -> str:
    """Render the useful portion of a terminal streaming failure."""
    error = getattr(event, "error", None)
    response = getattr(event, "response", None)
    details = error or getattr(response, "error", None) or response
    message = getattr(details, "message", None)
    return str(message or details or "Streaming response failed")


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


def is_output_limit_error(error: Exception) -> bool:
    """Recognize a terminal response cut off by its output-token allowance."""
    if isinstance(error, ProviderIncompleteError):
        return error.reason.casefold() in {
            "max_output_tokens",
            "max_tokens",
            "length",
        }
    rendered = str(error).casefold()
    return "max_output_tokens" in rendered or "maximum output" in rendered


def retryable_provider_error(error: Exception) -> bool:
    """Retry only transient transport and server failures."""
    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        return status in {408, 409, 429} or status >= 500
    name = type(error).__name__.casefold()
    return isinstance(error, (ConnectionError, TimeoutError)) or any(
        marker in name for marker in ("connection", "timeout", "ratelimit")
    )


def provider_retry_delay(error: Exception, attempt: int) -> float:
    """Return a bounded Retry-After or short exponential delay."""
    headers = getattr(error, "headers", None)
    value = None
    if headers is not None:
        getter = getattr(headers, "get", None)
        if callable(getter):
            value = getter("retry-after")
    try:
        retry_after = float(value) if value is not None else None
    except (TypeError, ValueError):
        retry_after = None
    if retry_after is not None:
        return max(0.0, min(30.0, retry_after))
    return min(4.0, 0.5 * (2 ** max(0, attempt - 1)))
