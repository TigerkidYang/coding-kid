from typing import Any

import coding_kid.cli as cli


def test_chat_accepts_input_shows_tool_activity_and_exits(monkeypatch: Any) -> None:
    inputs = iter(["Create a file", "/exit"])
    outputs: list[str] = []
    received_messages: list[list[Any]] = []

    def fake_input(prompt: str) -> str:
        outputs.append(prompt)
        return next(inputs)

    def fake_run_turn(messages: list[Any], on_tool: Any) -> str:
        received_messages.append(list(messages))
        on_tool("write", {"path": "hello.txt", "content": "hello"}, "Wrote hello.txt")
        return "Created hello.txt."

    monkeypatch.setattr(cli, "run_turn", fake_run_turn)

    cli.chat(input_function=fake_input, output_function=outputs.append)

    assert received_messages == [[{"role": "user", "content": "Create a file"}]]
    rendered = "\n".join(outputs)
    assert "Coding Kid" in rendered
    assert "[tool] write" in rendered
    assert "Wrote hello.txt" in rendered
    assert "Created hello.txt." in rendered


def test_chat_reports_an_error_and_keeps_running(monkeypatch: Any) -> None:
    inputs = iter(["broken task", "/exit"])
    outputs: list[str] = []

    def fake_run_turn(messages: list[Any], on_tool: Any) -> str:
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(cli, "run_turn", fake_run_turn)

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=outputs.append,
    )

    assert any("model unavailable" in line for line in outputs)
