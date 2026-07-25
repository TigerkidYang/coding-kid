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


def test_chat_handles_task_interruption_without_a_traceback(monkeypatch: Any) -> None:
    inputs = iter(["long task", "/exit"])
    outputs: list[str] = []

    def interrupted_run_turn(messages: list[Any], on_tool: Any) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_turn", interrupted_run_turn)

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=outputs.append,
    )

    assert any("Task interrupted" in line for line in outputs)
    assert outputs[-1] == "Goodbye."


def test_chat_rolls_back_a_failed_turn_before_continuing(monkeypatch: Any) -> None:
    inputs = iter(["first task", "second task", "/exit"])
    received_messages: list[list[Any]] = []

    def fake_run_turn(messages: list[Any], on_tool: Any) -> str:
        received_messages.append(list(messages))
        if len(received_messages) == 1:
            messages.append({"type": "partial-provider-output"})
            raise RuntimeError("failed")
        return "Second task completed."

    monkeypatch.setattr(cli, "run_turn", fake_run_turn)

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=lambda text: None,
    )

    assert received_messages[1] == [{"role": "user", "content": "second task"}]


def test_chat_preserves_successful_turns(monkeypatch: Any) -> None:
    inputs = iter(["first", "second", "/exit"])
    received_messages: list[list[Any]] = []

    def fake_run_turn(messages: list[Any], on_tool: Any) -> str:
        received_messages.append(list(messages))
        messages.append({"role": "assistant", "content": "done"})
        return "done"

    monkeypatch.setattr(cli, "run_turn", fake_run_turn)

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=lambda text: None,
    )

    assert received_messages[1] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "done"},
        {"role": "user", "content": "second"},
    ]


def test_chat_never_prints_a_blank_assistant_answer(monkeypatch: Any) -> None:
    inputs = iter(["answer me", "/exit"])
    outputs: list[str] = []

    monkeypatch.setattr(cli, "run_turn", lambda messages, on_tool: "   ")

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=outputs.append,
    )

    assert "Coding Kid>    " not in outputs
    assert any("empty" in line.lower() for line in outputs)


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
        (
            "todo",
            {
                "todos": [
                    {"content": "One", "status": "in_progress"},
                    {"content": "Two", "status": "completed"},
                ]
            },
            "[tool] todo: 2 items (1 in progress, 1 done)",
        ),
    ]

    for name, arguments, expected in cases:
        assert cli.format_tool_call(name, arguments) == expected


def test_chat_rolls_back_todos_with_a_failed_turn(monkeypatch: Any) -> None:
    from coding_kid.tools import get_todos, set_todos

    set_todos([{"content": "Keep me", "status": "pending"}])
    inputs = iter(["first task", "second task", "/exit"])
    received_messages: list[list[Any]] = []

    def fake_run_turn(messages: list[Any], on_tool: Any) -> str:
        received_messages.append(list(messages))
        if len(received_messages) == 1:
            set_todos([{"content": "Temporary", "status": "in_progress"}])
            raise RuntimeError("failed")
        return "Second task completed."

    monkeypatch.setattr(cli, "run_turn", fake_run_turn)

    cli.chat(
        input_function=lambda prompt: next(inputs),
        output_function=lambda text: None,
    )

    assert get_todos() == [{"content": "Keep me", "status": "pending"}]
    assert received_messages[1] == [{"role": "user", "content": "second task"}]


def test_format_tool_call_bounds_and_flattens_model_arguments() -> None:
    rendered = cli.format_tool_call("execute", {"command": "x\n" + "y" * 500})

    assert "\n" not in rendered
    assert len(rendered) <= 140
    assert rendered.endswith("...")


def test_format_search_call_displays_an_empty_path_as_current_directory() -> None:
    rendered = cli.format_tool_call("search", {"query": "def ", "path": ""})

    assert rendered == '[tool] search: "def " in .'
