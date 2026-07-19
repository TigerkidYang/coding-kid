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
        def __init__(self) -> None:
            self.responses = FakeResponses()

    monkeypatch.setattr(provider, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    messages = [{"role": "user", "content": "hello"}]
    tools = [{"type": "function", "name": "read"}]

    result = provider.generate("system", messages, tools)

    assert result is raw_response
    assert captured == {
        "model": "test-model",
        "instructions": "system",
        "input": messages,
        "tools": tools,
    }
