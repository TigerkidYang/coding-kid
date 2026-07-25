"""Live smoke: Coding Kid V02 should use todo on a multi-step local task.

Requires OPENROUTER_API_KEY and OPENROUTER_MODEL. This is not SWE-bench.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from coding_kid.agent import run_turn  # noqa: E402
from coding_kid.tools import clear_todos, get_todos  # noqa: E402


def main() -> int:
    if not os.getenv("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is not set", file=sys.stderr)
        return 1

    tool_calls: list[str] = []

    def on_tool(name: str, arguments: dict, result: str) -> None:
        tool_calls.append(name)
        preview = json.dumps(arguments, ensure_ascii=False)
        if len(preview) > 140:
            preview = preview[:137] + "..."
        print(f"[tool] {name} {preview}")
        if result.startswith("ERROR:"):
            print(result)

    prompt = (
        "Create a small Python package in the current directory with these steps:\n"
        "1) create package directory `demo_pkg` with `__init__.py`\n"
        "2) create `demo_pkg/mathutil.py` with an `add(a, b)` function\n"
        "3) create `tests/test_mathutil.py` that asserts `add(2, 3) == 5`\n"
        "4) run the test with pytest and report the result\n"
        "Use the todo tool to track these steps while you work."
    )

    clear_todos()
    with tempfile.TemporaryDirectory(prefix="ck-todo-smoke-") as tmp:
        work = Path(tmp)
        original = Path.cwd()
        try:
            os.chdir(work)
            answer = run_turn([{"role": "user", "content": prompt}], on_tool=on_tool)
            created_math = (work / "demo_pkg" / "mathutil.py").exists()
            created_test = (work / "tests" / "test_mathutil.py").exists()
            todos = get_todos()
        finally:
            os.chdir(original)
            clear_todos()

    print("--- answer ---")
    print(answer)
    print("--- checks ---")
    print(f"tool_calls={tool_calls}")
    print(f"final_todos={todos}")
    print(f"created_math={created_math} created_test={created_test}")

    failures: list[str] = []
    if "todo" not in tool_calls:
        failures.append("todo tool was never called")
    if "write" not in tool_calls:
        failures.append("write tool was never called")
    if not created_math:
        failures.append("demo_pkg/mathutil.py was not created")
    if not created_test:
        failures.append("tests/test_mathutil.py was not created")
    if not answer.strip():
        failures.append("empty final answer")

    if failures:
        print("FAIL")
        for item in failures:
            print(f"- {item}")
        return 1

    print("PASS live todo smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
