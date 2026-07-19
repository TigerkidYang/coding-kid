"""The plain terminal interface for Coding Kid."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from coding_kid.agent import run_turn

InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]


def format_tool_call(name: str, arguments: dict[str, Any]) -> str:
    """Describe a tool action without exposing its input or output contents."""
    if name == "execute":
        return f"[tool] execute: {arguments.get('command', '?')}"
    if name == "search":
        query = arguments.get("query", "?")
        path = arguments.get("path", ".")
        return f'[tool] search: "{query}" in {path}'
    if name in {"read", "write", "patch", "delete"}:
        return f"[tool] {name}: {arguments.get('path', '?')}"
    return f"[tool] {name}"


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

        messages.append({"role": "user", "content": user_input})
        try:
            answer = run_turn(messages, on_tool=show_tool)
        except Exception as error:
            output_function(f"Error: {error}")
            continue

        output_function(f"Coding Kid> {answer}")


def main() -> None:
    """Start the terminal chat."""
    chat()
