"""Send model requests through an OpenAI-compatible Responses API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from openai import OpenAI

from coding_kid.events import CancellationToken

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
PROVIDER_BASE_URL_ENV = "CODING_KID_PROVIDER_BASE_URL"
REASONING_EFFORT_ENV = "CODING_KID_REASONING_EFFORT"
DISABLE_MAX_OUTPUT_TOKENS_ENV = "CODING_KID_DISABLE_MAX_OUTPUT_TOKENS"
PROVIDER_TIMEOUT_ENV = "CODING_KID_PROVIDER_TIMEOUT_SECONDS"


class ProviderIncompleteError(RuntimeError):
    """A streaming response ended intentionally before a complete response."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Streaming response incomplete: {reason}")
        self.reason = reason


class ProviderProtocolError(RuntimeError):
    """The compatible endpoint or SDK returned an unusable protocol shape."""


def is_null_collection_error(error: BaseException) -> bool:
    """Recognize the compatible Responses SDK's observed null iterable defect."""
    rendered = str(error).casefold()
    return (
        isinstance(error, TypeError)
        and "nonetype" in rendered
        and "iterable" in rendered
    )


def _raise_protocol_error(error: TypeError) -> None:
    """Translate the observed null-collection SDK failure into a retryable error."""
    if not is_null_collection_error(error):
        raise error
    raise ProviderProtocolError(
        "Provider returned a null collection where the Responses protocol requires "
        "an iterable value"
    ) from error


def required_environment(name: str) -> str:
    """Read one required setting and fail with a useful message if absent."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def provider_base_url() -> str:
    """Return the configured OpenAI-compatible Responses API base URL."""
    return os.getenv(PROVIDER_BASE_URL_ENV, OPENROUTER_BASE_URL).rstrip("/")


def provider_timeout() -> float:
    """Return the request timeout, retaining the historical default."""
    raw = os.getenv(PROVIDER_TIMEOUT_ENV, "120").strip()
    try:
        value = float(raw)
    except ValueError as error:
        raise RuntimeError(f"{PROVIDER_TIMEOUT_ENV} must be a number") from error
    if value <= 0:
        raise RuntimeError(f"{PROVIDER_TIMEOUT_ENV} must be positive")
    return value


def _enabled(name: str) -> bool:
    value = os.getenv(name, "").strip().casefold()
    return value in {"1", "true", "yes", "on"}


def _request_options(max_output_tokens: int | None) -> dict[str, Any]:
    """Build optional provider parameters without changing default behavior."""
    options: dict[str, Any] = {}
    effort = os.getenv(REASONING_EFFORT_ENV, "").strip()
    if effort:
        options["reasoning"] = {"effort": effort}
    if max_output_tokens is not None and not _enabled(DISABLE_MAX_OUTPUT_TOKENS_ENV):
        options["max_output_tokens"] = max_output_tokens
    return options


def generate(
    instructions: str,
    messages: list[Any],
    tools: list[dict[str, Any]],
    *,
    max_output_tokens: int | None = None,
) -> Any:
    """Send the current context and return the provider's raw response."""
    client = OpenAI(
        api_key=required_environment("OPENROUTER_API_KEY"),
        base_url=provider_base_url(),
        timeout=provider_timeout(),
        max_retries=0,
    )
    request: dict[str, Any] = {
        "model": required_environment("OPENROUTER_MODEL"),
        "instructions": instructions,
        "input": messages,
        "tools": tools,
    }
    request.update(_request_options(max_output_tokens))
    try:
        return client.responses.create(**request)
    except TypeError as error:
        _raise_protocol_error(error)


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
        base_url=provider_base_url(),
        timeout=provider_timeout(),
        max_retries=0,
    )
    request: dict[str, Any] = {
        "model": required_environment("OPENROUTER_MODEL"),
        "instructions": instructions,
        "input": messages,
        "tools": tools,
        "stream": True,
    }
    request.update(_request_options(max_output_tokens))

    try:
        stream = client.responses.create(**request)
    except TypeError as error:
        _raise_protocol_error(error)
    if stream is None:
        raise ProviderProtocolError("Provider returned no streaming response object")
    final_response: Any | None = None
    try:
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
        except TypeError as error:
            _raise_protocol_error(error)
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            try:
                close()
            except TypeError as error:
                _raise_protocol_error(error)

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
    """Return the provider's context length for one exact model slug."""
    headers = {"Accept": "application/json"}
    api_key = os.getenv("OPENROUTER_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        f"{provider_base_url()}/models",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
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
    if isinstance(error, ProviderProtocolError):
        return True
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
