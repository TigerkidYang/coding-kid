from typing import Any

import coding_kid.provider as provider


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
