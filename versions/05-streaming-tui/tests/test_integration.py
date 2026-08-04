import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from coding_kid.agent import run_turn


def function_call(
    call_id: str, name: str, arguments: dict[str, Any]
) -> SimpleNamespace:
    return SimpleNamespace(
        type="function_call",
        call_id=call_id,
        name=name,
        arguments=json.dumps(arguments),
    )


def test_complete_agent_file_workflow(tmp_path: Path) -> None:
    """Prove the loop can perform a multi-step task with the real tools."""
    file_path = tmp_path / "lesson.txt"
    responses = iter(
        [
            SimpleNamespace(
                output=[
                    function_call(
                        "write-1",
                        "write",
                        {"path": str(file_path), "content": "version one"},
                    )
                ]
            ),
            SimpleNamespace(
                output=[
                    function_call(
                        "patch-1",
                        "patch",
                        {
                            "path": str(file_path),
                            "old_text": "one",
                            "new_text": "two",
                        },
                    )
                ]
            ),
            SimpleNamespace(
                output=[function_call("read-1", "read", {"path": str(file_path)})]
            ),
            SimpleNamespace(
                output=[function_call("delete-1", "delete", {"path": str(file_path)})]
            ),
            SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="message",
                        content=[
                            SimpleNamespace(
                                type="output_text", text="Workflow complete."
                            )
                        ],
                    )
                ]
            ),
        ]
    )
    observed: list[tuple[str, str]] = []

    def fake_provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
    ) -> SimpleNamespace:
        return next(responses)

    final_text = run_turn(
        [{"role": "user", "content": "Complete the file workflow"}],
        fake_provider,
        on_tool=lambda name, arguments, result: observed.append((name, result)),
    )

    assert final_text == "Workflow complete."
    assert [name for name, _ in observed] == ["write", "patch", "read", "delete"]
    assert observed[2][1] == "version two"
    assert not file_path.exists()
