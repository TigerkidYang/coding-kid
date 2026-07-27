"""Run Coding Kid Version 01 against selected eval tasks and record outcomes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from coding_kid.agent import run_turn  # noqa: E402

WORKSPACES = Path(__file__).resolve().parent / "workspaces"
FIXTURES = (
    Path(__file__).resolve().parent
    / "AgentBench-Live"
    / "tasks"
    / "fixtures"
)
REPORT_PATH = Path(__file__).resolve().parent / "v1_baseline_report.json"


@dataclass
class TaskResult:
    task_id: str
    passed_outcome: bool
    duration_s: float
    tool_calls: list[str] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)
    answer_preview: str = ""
    pytest_summary: str = ""
    notes: list[str] = field(default_factory=list)
    error: str | None = None
    used_todo: bool = False
    checklist_signals: list[str] = field(default_factory=list)


def reset_workspace(name: str) -> Path:
    src = FIXTURES / name
    dst = WORKSPACES / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return dst


def run_pytest(workspace: Path, args: list[str]) -> tuple[bool, str]:
    cmd = [
        "uv",
        "run",
        "--directory",
        str(ROOT),
        "--extra",
        "dev",
        "pytest",
        *args,
        "-q",
        "--tb=line",
        "-o",
        "addopts=",
        f"--rootdir={workspace}",
    ]
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=workspace,
    )
    output = (completed.stdout + completed.stderr).strip()
    summary_lines = [
        line
        for line in output.splitlines()
        if "passed" in line or "failed" in line or "ERROR" in line
    ]
    summary = " | ".join(summary_lines[-3:]) if summary_lines else output[-500:]
    return completed.returncode == 0, summary


def run_agent(prompt: str, workspace: Path) -> TaskResult:
    """Placeholder filled by callers that know task_id."""
    raise NotImplementedError


def execute_task(task_id: str, prompt: str, workspace: Path, verify) -> TaskResult:
    original = Path.cwd()
    tool_calls: list[str] = []
    tool_errors: list[str] = []
    start = time.perf_counter()
    answer = ""
    notes: list[str] = []
    checklist_signals: list[str] = []

    def on_tool(name: str, arguments: dict, result: str) -> None:
        tool_calls.append(name)
        if name in {"todo", "todo_write"}:
            notes.append("unexpected todo tool on V01")
        if result.startswith("ERROR:"):
            tool_errors.append(f"{name}: {result[:160]}")
        # Process signals: did the model write an explicit plan file?
        if name == "write" and "plan" in str(arguments.get("path", "")).lower():
            checklist_signals.append("wrote_plan_file")
        if name == "execute" and "pytest" in str(arguments.get("command", "")).lower():
            checklist_signals.append("ran_pytest")

    try:
        os.chdir(workspace)
        messages = [{"role": "user", "content": prompt}]
        answer = run_turn(messages, on_tool=on_tool)
        outcome_ok, pytest_summary = verify(workspace)
        # Process heuristic for V01: ordered multi-phase tool use
        if checklist_signals.count("ran_pytest") >= 2:
            checklist_signals.append("pytest_before_and_after")
        if len(set(tool_calls)) >= 3 and "write" in tool_calls or "patch" in tool_calls:
            if "read" in tool_calls and "ran_pytest" in checklist_signals:
                checklist_signals.append("read_edit_verify_pattern")

        return TaskResult(
            task_id=task_id,
            passed_outcome=outcome_ok,
            duration_s=time.perf_counter() - start,
            tool_calls=tool_calls,
            tool_errors=tool_errors,
            answer_preview=answer[:500],
            pytest_summary=pytest_summary,
            notes=notes,
            used_todo=False,
            checklist_signals=checklist_signals,
        )
    except Exception as exc:
        return TaskResult(
            task_id=task_id,
            passed_outcome=False,
            duration_s=time.perf_counter() - start,
            tool_calls=tool_calls,
            tool_errors=tool_errors,
            answer_preview=answer[:500],
            notes=notes,
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-800:]}",
            checklist_signals=checklist_signals,
        )
    finally:
        os.chdir(original)


def verify_multi_001(workspace: Path) -> tuple[bool, str]:
    ok, summary = run_pytest(
        workspace,
        ["tests", "--override-ini=pythonpath=."],
    )
    changelog = workspace / "CHANGELOG.md"
    has_changelog = changelog.exists() and changelog.stat().st_size > 0
    if ok and has_changelog:
        return True, summary + " | CHANGELOG.md present"
    if ok and not has_changelog:
        return False, summary + " | MISSING CHANGELOG.md"
    return False, summary + (
        " | CHANGELOG.md present" if has_changelog else " | MISSING CHANGELOG.md"
    )


def verify_code_001(workspace: Path) -> tuple[bool, str]:
    return run_pytest(workspace, ["test_paginator.py"])


def verify_multi_002(workspace: Path) -> tuple[bool, str]:
    remote = workspace / "config" / "remote.py"
    tests = workspace / "tests" / "test_remote_config.py"
    notes = []
    if not remote.exists():
        notes.append("MISSING config/remote.py")
    if not tests.exists():
        notes.append("MISSING tests/test_remote_config.py")
    ok, summary = run_pytest(
        workspace,
        ["tests", "--override-ini=pythonpath=."],
    )
    if notes:
        return False, summary + " | " + " | ".join(notes)
    return ok, summary


def main() -> int:
    if not os.getenv("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is not set")
        return 1

    tasks = [
        {
            "id": "agentbench-code-001",
            "reset": "code-001",
            "prompt": """The file paginator.py in the current directory implements a simple list paginator.
Users report that requesting page 2 returns the same items as page 1.

1. Read the code and identify the bug.
2. Fix it.
3. Run pytest on test_paginator.py to verify your fix passes all tests.
Do not modify the tests.""",
            "verify": verify_code_001,
        },
        {
            "id": "agentbench-multi-001",
            "reset": "multi-001",
            "prompt": """The project in the current directory has failing tests. Your workflow:

1. Run pytest on the tests/ directory to see which tests fail.
2. Read the test files and source code to understand the failures.
3. Fix the bugs in the source code (do NOT modify the tests).
4. Re-run pytest on tests/ to confirm all tests pass.
5. Generate a file CHANGELOG.md describing what you fixed, following Keep a Changelog format.

All bugs are in different source files under src/. The tests are correct.
Use Windows commands where needed. The package imports use `src.` as the package prefix.""",
            "verify": verify_multi_001,
        },
        {
            "id": "agentbench-multi-002",
            "reset": "multi-002",
            "prompt": """The project in the current directory is a CLI tool that currently reads config from a YAML/JSON file.
Add a new config source: fetching config from a remote HTTP endpoint.

Workflow:
1. Read the existing codebase to understand the config loading architecture.
2. Research httpx usage if needed (you may already know it).
3. Implement a new RemoteConfigLoader class in config/remote.py that:
   - Fetches JSON config from a URL passed as parameter
   - Validates the response using the existing Pydantic config schema
   - Handles timeouts (5s), retries (2 attempts), and invalid JSON gracefully
   - Integrates with the existing ConfigManager in config/manager.py
4. Write tests in tests/test_remote_config.py covering:
   - Successful fetch and parse
   - Timeout handling
   - Invalid JSON response
   - HTTP error responses
5. Add a brief section to README.md documenting the remote config feature.

Verify: pytest on tests/ must pass (both existing and new tests).
Use Windows commands where needed.""",
            "verify": verify_multi_002,
        },
    ]

    results: list[TaskResult] = []
    for spec in tasks:
        print(f"\n=== Running {spec['id']} ===")
        workspace = reset_workspace(spec["reset"])
        result = execute_task(spec["id"], spec["prompt"], workspace, spec["verify"])
        results.append(result)
        status = "PASS" if result.passed_outcome else "FAIL"
        print(
            f"[{status}] {result.duration_s:.1f}s | tools={result.tool_calls} | "
            f"signals={result.checklist_signals}"
        )
        print(f"pytest: {result.pytest_summary}")
        if result.error:
            print(f"error: {result.error[:400]}")
        print(f"answer: {result.answer_preview[:200]!r}")

    REPORT_PATH.write_text(
        json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nReport written to {REPORT_PATH}")
    passed = sum(1 for r in results if r.passed_outcome)
    print(f"Outcome: {passed}/{len(results)} passed on Coding Kid V01")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
