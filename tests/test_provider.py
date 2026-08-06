from io import BytesIO
from types import SimpleNamespace
from typing import Any

import coding_kid.provider as provider
import pytest
from coding_kid.events import CancellationToken, TurnCancelled


def test_generate_sends_inputs_and_returns_raw_response(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}
    raw_response = object()

    class FakeResponses:
        def create(self, **kwargs: Any) -> object:
            captured.update(kwargs)
            return raw_response

    class FakeOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured["client"] = kwargs
            self.responses = FakeResponses()

    monkeypatch.setattr(provider, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")
    messages = [{"role": "user", "content": "hello"}]
    tools = [{"type": "function", "name": "read"}]

    result = provider.generate("system", messages, tools)

    assert result is raw_response
    assert captured.pop("client") == {
        "api_key": "test-key",
        "base_url": "https://openrouter.ai/api/v1",
        "timeout": 120.0,
        "max_retries": 0,
    }
    assert captured == {
        "model": "test/model",
        "instructions": "system",
        "input": messages,
        "tools": tools,
    }


def test_generate_requires_openrouter_environment(monkeypatch: Any) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    try:
        provider.generate("system", [], [])
    except RuntimeError as error:
        assert "OPENROUTER_API_KEY" in str(error)
    else:
        raise AssertionError("missing OpenRouter configuration should fail")


def test_generate_requires_a_model_when_the_key_exists(monkeypatch: Any) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    try:
        provider.generate("system", [], [])
    except RuntimeError as error:
        assert "OPENROUTER_MODEL" in str(error)
    else:
        raise AssertionError("missing model configuration should fail")


def test_generate_passes_optional_output_limit(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    class FakeResponses:
        def create(self, **kwargs: Any) -> object:
            captured.update(kwargs)
            return object()

    class FakeOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            self.responses = FakeResponses()

    monkeypatch.setattr(provider, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")

    provider.generate("system", [], [], max_output_tokens=4096)

    assert captured["max_output_tokens"] == 4096


def test_generate_supports_compatible_base_url_and_reasoning(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}

    class FakeResponses:
        def create(self, **kwargs: Any) -> object:
            captured["request"] = kwargs
            return object()

    class FakeOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured["client"] = kwargs
            self.responses = FakeResponses()

    monkeypatch.setattr(provider, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv(
        "CODING_KID_PROVIDER_BASE_URL", "http://192.168.110.224:8787/v1/"
    )
    monkeypatch.setenv("CODING_KID_REASONING_EFFORT", "max")
    monkeypatch.setenv("CODING_KID_DISABLE_MAX_OUTPUT_TOKENS", "true")

    provider.generate("system", [], [], max_output_tokens=4096)

    assert captured["client"]["base_url"] == "http://192.168.110.224:8787/v1"
    assert captured["request"]["reasoning"] == {"effort": "max"}
    assert "max_output_tokens" not in captured["request"]


def test_generate_streaming_forwards_deltas_and_returns_terminal_response(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}
    final_response = SimpleNamespace(output=[], usage=None)

    class FakeStream:
        closed = False

        def __iter__(self):
            return iter(
                [
                    SimpleNamespace(type="response.output_text.delta", delta="Hel"),
                    SimpleNamespace(type="response.content_part.delta", delta="lo"),
                    SimpleNamespace(type="response.completed", response=final_response),
                ]
            )

        def close(self) -> None:
            self.closed = True

    stream = FakeStream()

    class FakeResponses:
        def create(self, **kwargs: Any) -> FakeStream:
            captured.update(kwargs)
            return stream

    class FakeOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            self.responses = FakeResponses()

    monkeypatch.setattr(provider, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")
    deltas: list[str] = []

    result = provider.generate_streaming("system", [], [], on_text_delta=deltas.append)

    assert result is final_response
    assert deltas == ["Hel", "lo"]
    assert captured["stream"] is True
    assert stream.closed


def test_generate_streaming_accepts_openrouter_done_event(monkeypatch: Any) -> None:
    final_response = object()

    class FakeResponses:
        def create(self, **kwargs: Any) -> Any:
            return iter(
                [SimpleNamespace(type="response.done", response=final_response)]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            self.responses = FakeResponses()

    monkeypatch.setattr(provider, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")

    assert (
        provider.generate_streaming("system", [], [], on_text_delta=lambda _: None)
        is final_response
    )


def test_generate_streaming_rejects_failure_and_missing_terminal(
    monkeypatch: Any,
) -> None:
    streams = iter(
        [
            iter(
                [
                    SimpleNamespace(
                        type="response.failed",
                        error=SimpleNamespace(message="provider failed"),
                    )
                ]
            ),
            iter([SimpleNamespace(type="response.output_text.delta", delta="partial")]),
        ]
    )

    class FakeResponses:
        def create(self, **kwargs: Any) -> Any:
            return next(streams)

    class FakeOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            self.responses = FakeResponses()

    monkeypatch.setattr(provider, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")

    with pytest.raises(RuntimeError, match="provider failed"):
        provider.generate_streaming("system", [], [], on_text_delta=lambda _: None)
    with pytest.raises(RuntimeError, match="without a terminal response"):
        provider.generate_streaming("system", [], [], on_text_delta=lambda _: None)


def test_generate_streaming_classifies_output_limit_incomplete(
    monkeypatch: Any,
) -> None:
    incomplete = SimpleNamespace(
        type="response.incomplete",
        response=SimpleNamespace(
            incomplete_details=SimpleNamespace(reason="max_output_tokens")
        ),
    )

    class FakeResponses:
        def create(self, **kwargs: Any) -> Any:
            return iter([incomplete])

    class FakeOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            self.responses = FakeResponses()

    monkeypatch.setattr(provider, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")

    with pytest.raises(provider.ProviderIncompleteError) as raised:
        provider.generate_streaming("system", [], [], on_text_delta=lambda _: None)
    assert raised.value.reason == "max_output_tokens"
    assert provider.is_output_limit_error(raised.value)


def test_generate_streaming_honors_cancellation(monkeypatch: Any) -> None:
    token = CancellationToken()

    class FakeStream:
        closed = False

        def __iter__(self):
            token.cancel()
            yield SimpleNamespace(type="response.output_text.delta", delta="ignored")

        def close(self) -> None:
            self.closed = True

    stream = FakeStream()

    class FakeResponses:
        def create(self, **kwargs: Any) -> FakeStream:
            return stream

    class FakeOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            self.responses = FakeResponses()

    monkeypatch.setattr(provider, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")

    with pytest.raises(TurnCancelled):
        provider.generate_streaming(
            "system", [], [], on_text_delta=lambda _: None, cancellation_token=token
        )
    assert stream.closed


def test_discover_context_length_matches_exact_model(monkeypatch: Any) -> None:
    payload = b'{"data":[{"id":"test/model","context_length":128000}]}'
    monkeypatch.setattr(
        provider.urllib.request,
        "urlopen",
        lambda *args, **kwargs: BytesIO(payload),
    )

    assert provider.discover_context_length("test/model") == 128000
    assert provider.discover_context_length("missing/model") is None


def test_response_usage_and_context_error_classification() -> None:
    response = SimpleNamespace(usage=SimpleNamespace(input_tokens=123))

    assert provider.response_input_tokens(response) == 123
    assert provider.response_input_tokens(SimpleNamespace()) is None
    assert provider.is_context_window_error(
        RuntimeError("maximum context length exceeded")
    )
    assert not provider.is_context_window_error(RuntimeError("authentication failed"))


def test_provider_retry_classification_and_bounded_delay() -> None:
    transient = RuntimeError("server")
    transient.status_code = 503  # type: ignore[attr-defined]
    limited = RuntimeError("limited")
    limited.status_code = 429  # type: ignore[attr-defined]
    limited.headers = {"retry-after": "90"}  # type: ignore[attr-defined]

    assert provider.retryable_provider_error(transient)
    assert provider.retryable_provider_error(limited)
    assert provider.provider_retry_delay(limited, 1) == 30.0
    assert not provider.retryable_provider_error(RuntimeError("bad request"))
