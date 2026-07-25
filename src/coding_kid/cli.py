"""The plain terminal interface for Coding Kid."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from coding_kid.agent import run_turn
from coding_kid.tools import get_todos, set_todos

InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]
MAX_TOOL_DISPLAY_CHARS = 140


def format_tool_call(name: str, arguments: dict[str, Any]) -> str:
    """Describe a tool action without exposing its input or output contents."""
    if name == "execute":
        rendered = f"[tool] execute: {arguments.get('command', '?')}"
    elif name == "search":
        query = arguments.get("query", "?")
        path = arguments.get("path") or "."
        rendered = f'[tool] search: "{query}" in {path}'
    elif name in {"read", "write", "patch", "delete"}:
        rendered = f"[tool] {name}: {arguments.get('path', '?')}"
    elif name == "todo":
        items = arguments.get("todos")
        if not isinstance(items, list):
            rendered = "[tool] todo"
        else:
            in_progress = sum(
                1
                for item in items
                if isinstance(item, dict) and item.get("status") == "in_progress"
            )
            completed = sum(
                1
                for item in items
                if isinstance(item, dict) and item.get("status") == "completed"
            )
            rendered = (
                f"[tool] todo: {len(items)} items "
                f"({in_progress} in progress, {completed} done)"
            )
    else:
        rendered = f"[tool] {name}"

    rendered = " ".join(str(rendered).splitlines())
    if len(rendered) > MAX_TOOL_DISPLAY_CHARS:
        return f"{rendered[: MAX_TOOL_DISPLAY_CHARS - 3]}..."
    return rendered


def chat(
    input_function: InputFunction = input,
    output_function: OutputFunction = print,
) -> None:
    """Keep accepting user messages until the user exits."""
    messages: list[Any] = []
    output_function("Coding Kid is ready. Type /exit to quit.")

    def show_tool(name: str, arguments: dict[str, Any], result: str) -> None:
        output_function(format_tool_call(name, arguments))
        if result.startswith("ERROR:"):
            output_function(result)

    while True:
        try:
            user_input = input_function("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            output_function("\nGoodbye.")
            return

        if user_input in {"/exit", "/quit"}:
            output_function("Goodbye.")
            return
        if not user_input:
            continue

        turn_start = len(messages)
        todos_start = get_todos()
        messages.append({"role": "user", "content": user_input})
        try:
            answer = run_turn(messages, on_tool=show_tool)
            if not answer.strip():
                raise RuntimeError("Model returned an empty answer")
        except KeyboardInterrupt:
            del messages[turn_start:]
            set_todos(todos_start)
            output_function("\nTask interrupted. You can enter another request.")
            continue
        except Exception as error:
            del messages[turn_start:]
            set_todos(todos_start)
            output_function(f"Error: {error}")
            continue

        output_function(f"Coding Kid> {answer}")


def main() -> None:
    """Start the terminal chat."""
    chat()
