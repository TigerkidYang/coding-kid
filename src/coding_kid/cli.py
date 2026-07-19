"""The plain terminal interface for Coding Kid."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from coding_kid.agent import run_turn

InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]


def chat(
    input_function: InputFunction = input,
    output_function: OutputFunction = print,
) -> None:
    """Keep accepting user messages until the user exits."""
    messages: list[Any] = []
    output_function("Coding Kid is ready. Type /exit to quit.")

    def show_tool(name: str, arguments: dict[str, Any], result: str) -> None:
        rendered_arguments = json.dumps(arguments, ensure_ascii=False)
        output_function(f"[tool] {name} {rendered_arguments}")
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
