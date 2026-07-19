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
    assert "[tool] write: hello.txt" in rendered
    assert '"content": "hello"' not in rendered
    assert "Wrote hello.txt" not in rendered
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


def test_chat_hides_tool_results_but_shows_tool_errors(monkeypatch: Any) -> None:
    inputs = iter(["inspect files", "/exit"])
    outputs: list[str] = []

    def fake_run_turn(messages: list[Any], on_tool: Any) -> str:
        on_tool(
            "read",
            {"path": "secret.txt"},
            "the complete private file contents",
        )
        on_tool(
            "patch",
            {
                "path": "missing.txt",
                "old_text": "large old content",
                "new_text": "large new content",
            },
            "ERROR: FileNotFoundError: missing.txt",
        )
        return "Inspection finished."

    monkeypatch.setattr(cli, "run_turn", fake_run_turn)

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=outputs.append,
    )

    rendered = "\n".join(outputs)
    assert "[tool] read: secret.txt" in rendered
    assert "[tool] patch: missing.txt" in rendered
    assert "complete private file contents" not in rendered
    assert "large old content" not in rendered
    assert "large new content" not in rendered
    assert "ERROR: FileNotFoundError: missing.txt" in rendered


def test_format_tool_call_keeps_each_action_compact() -> None:
    cases = [
        ("execute", {"command": "pytest"}, "[tool] execute: pytest"),
        ("read", {"path": "app.py"}, "[tool] read: app.py"),
        (
            "search",
            {"query": "needle", "path": "src"},
            '[tool] search: "needle" in src',
        ),
        ("write", {"path": "new.py", "content": "hidden"}, "[tool] write: new.py"),
        (
            "patch",
            {"path": "app.py", "old_text": "hidden", "new_text": "hidden"},
            "[tool] patch: app.py",
        ),
        ("delete", {"path": "old.py"}, "[tool] delete: old.py"),
    ]

    for name, arguments, expected in cases:
        assert cli.format_tool_call(name, arguments) == expected
