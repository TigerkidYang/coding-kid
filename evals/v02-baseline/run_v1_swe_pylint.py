"""Run Coding Kid V01 on one real SWE-bench Lite instance (pylint-6506)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"

from coding_kid.agent import run_turn  # noqa: E402

WORKSPACE = Path(__file__).resolve().parent / "swe-pylint-full"
REPORT = Path(__file__).resolve().parent / "v1_swe_pylint_6506_report.json"

PROMPT = """\
Traceback printed for unrecognized option

### Bug description
A traceback is printed when an unrecognized option is passed to pylint.

### Command used
```shell
pylint -Q
```

### Expected behavior
The command should exit cleanly with a usage/error message for the unrecognized
option. It should NOT print an internal Python traceback from
`_UnrecognizedOptionError`.

### Actual behavior
Pylint emits E0015 and then raises `_UnrecognizedOptionError`, producing a
traceback.

Fix this bug in the pylint codebase in the current directory. The failing tests
are:
- tests/config/test_config.py::test_unknown_option_name
- tests/config/test_config.py::test_unknown_short_option_name

Do not modify the tests. Make those tests pass.
"""


def run_fail_tests() -> tuple[bool, str]:
    completed = subprocess.run(
        [
            str(VENV_PY),
            "-m",
            "pytest",
            "tests/config/test_config.py::test_unknown_option_name",
            "tests/config/test_config.py::test_unknown_short_option_name",
            "-q",
            "--tb=line",
        ],
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (completed.stdout + completed.stderr).strip()
    return completed.returncode == 0, " | ".join(out.splitlines()[-8:])


def main() -> int:
    if not os.getenv("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY missing")
        return 1

    before_ok, before = run_fail_tests()
    print(f"BEFORE agent: ok={before_ok}")
    print(before)
    if before_ok:
        print("Tests already pass; cannot use as failing baseline")
        return 1

    tool_calls: list[str] = []
    tool_errors: list[str] = []
    start = time.perf_counter()
    original = Path.cwd()
    answer = ""
    error = None

    def on_tool(name: str, arguments: dict, result: str) -> None:
        tool_calls.append(name)
        print(f"  [tool] {name}: {arguments}")
        if result.startswith("ERROR:"):
            tool_errors.append(result[:200])
            print(f"  ERROR {result[:200]}")

    try:
        os.chdir(WORKSPACE)
        answer = run_turn(
            [{"role": "user", "content": PROMPT}],
            on_tool=on_tool,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-800:]}"
    finally:
        os.chdir(original)

    after_ok, after = run_fail_tests()
    report = {
        "instance_id": "pylint-dev__pylint-6506",
        "source": "SWE-bench/SWE-bench_Lite",
        "passed_outcome": after_ok,
        "duration_s": time.perf_counter() - start,
        "tool_calls": tool_calls,
        "tool_errors": tool_errors,
        "before": before,
        "after": after,
        "answer_preview": answer[:800],
        "error": error,
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nAFTER agent: ok={after_ok}")
    print(after)
    print(f"tools={tool_calls}")
    print(f"answer: {answer[:300]!r}")
    if error:
        print(f"error: {error[:400]}")
    print(f"Report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
