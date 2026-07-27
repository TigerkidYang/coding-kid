"""V01 baseline round 2: harder prompts + one SWE-bench-style local task.

AgentBench prompts already list numbered steps. That leaks task decomposition
into the user message. Round 2 removes the checklist and keeps only the goal.
"""

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
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"

from coding_kid.agent import run_turn  # noqa: E402

BASE = Path(__file__).resolve().parent
WORKSPACES = BASE / "workspaces"
FIXTURES = BASE / "AgentBench-Live" / "tasks" / "fixtures"
REPORT_PATH = BASE / "v1_baseline_round2_report.json"


@dataclass
class TaskResult:
    task_id: str
    passed_outcome: bool
    duration_s: float
    tool_calls: list[str] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)
    answer_preview: str = ""
    verify_summary: str = ""
    error: str | None = None
    process_notes: list[str] = field(default_factory=list)


def reset_workspace(name: str) -> Path:
    src = FIXTURES / name
    dst = WORKSPACES / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return dst


def isolated_pytest(workspace: Path, target: str) -> tuple[bool, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(workspace)
    completed = subprocess.run(
        [
            str(VENV_PY),
            "-m",
            "pytest",
            target,
            "-q",
            "--tb=line",
            "-p",
            "no:cacheprovider",
            "--noconftest",
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    out = (completed.stdout + completed.stderr).strip()
    tail = " | ".join(out.splitlines()[-5:])
    return completed.returncode == 0, tail


def execute_task(task_id: str, prompt: str, workspace: Path, verify) -> TaskResult:
    original = Path.cwd()
    tool_calls: list[str] = []
    tool_errors: list[str] = []
    process_notes: list[str] = []
    start = time.perf_counter()
    answer = ""

    def on_tool(name: str, arguments: dict, result: str) -> None:
        tool_calls.append(name)
        if result.startswith("ERROR:"):
            tool_errors.append(f"{name}: {result[:160]}")
        cmd = str(arguments.get("command", ""))
        if name == "execute" and "pytest" in cmd.lower():
            process_notes.append("ran_pytest")
        if name in {"write", "patch"}:
            process_notes.append(f"edit:{arguments.get('path', '?')}")

    try:
        os.chdir(workspace)
        messages = [{"role": "user", "content": prompt}]
        answer = run_turn(messages, on_tool=on_tool)
        ok, summary = verify(workspace)
        return TaskResult(
            task_id=task_id,
            passed_outcome=ok,
            duration_s=time.perf_counter() - start,
            tool_calls=tool_calls,
            tool_errors=tool_errors,
            answer_preview=answer[:500],
            verify_summary=summary,
            process_notes=process_notes,
        )
    except Exception as exc:
        return TaskResult(
            task_id=task_id,
            passed_outcome=False,
            duration_s=time.perf_counter() - start,
            tool_calls=tool_calls,
            tool_errors=tool_errors,
            answer_preview=answer[:500],
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-700:]}",
            process_notes=process_notes,
        )
    finally:
        os.chdir(original)


def verify_multi_001(workspace: Path) -> tuple[bool, str]:
    ok, summary = isolated_pytest(workspace, "tests")
    changelog = workspace / "CHANGELOG.md"
    has_cl = changelog.exists() and changelog.stat().st_size > 20
    if ok and has_cl:
        return True, summary + " | CHANGELOG ok"
    if ok:
        return False, summary + " | MISSING/short CHANGELOG"
    return False, summary + (" | CHANGELOG ok" if has_cl else " | MISSING CHANGELOG")


def verify_code_001(workspace: Path) -> tuple[bool, str]:
    return isolated_pytest(workspace, "test_paginator.py")


def verify_multi_002(workspace: Path) -> tuple[bool, str]:
    missing = []
    if not (workspace / "config" / "remote.py").exists():
        missing.append("no remote.py")
    if not (workspace / "tests" / "test_remote_config.py").exists():
        missing.append("no test_remote_config.py")
    ok, summary = isolated_pytest(workspace, "tests")
    if missing:
        return False, summary + " | " + ", ".join(missing)
    return ok, summary


def main() -> int:
    if not os.getenv("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is not set")
        return 1

    results: list[TaskResult] = []

    # Round-2 AgentBench prompts: goal only, no numbered workflow leakage.
    goal_tasks = [
        {
            "id": "code-001-goal-only",
            "reset": "code-001",
            "prompt": (
                "paginator.py has a pagination bug: page 2 returns the same "
                "items as page 1. Fix the bug and make sure the tests pass."
            ),
            "verify": verify_code_001,
        },
        {
            "id": "multi-001-goal-only",
            "reset": "multi-001",
            "prompt": (
                "This project has failing unit tests caused by bugs in src/. "
                "Fix the source bugs (do not change tests), make all tests "
                "pass, and write a CHANGELOG.md summarizing the fixes."
            ),
            "verify": verify_multi_001,
        },
        {
            "id": "multi-002-goal-only",
            "reset": "multi-002",
            "prompt": (
                "Extend this config system with a RemoteConfigLoader in "
                "config/remote.py that fetches JSON over HTTP with httpx "
                "(5s timeout, 2 retries), validates with the existing "
                "Pydantic schema, integrates with ConfigManager, includes "
                "tests in tests/test_remote_config.py for success/timeout/"
                "invalid JSON/HTTP errors, documents it in README.md, and "
                "make sure pytest passes."
            ),
            "verify": verify_multi_002,
        },
    ]

    for spec in goal_tasks:
        print(f"\n=== {spec['id']} ===")
        workspace = reset_workspace(spec["reset"])
        result = execute_task(spec["id"], spec["prompt"], workspace, spec["verify"])
        results.append(result)
        mark = "PASS" if result.passed_outcome else "FAIL"
        print(
            f"[{mark}] {result.duration_s:.1f}s tools={result.tool_calls} "
            f"notes={result.process_notes}"
        )
        print(f"verify: {result.verify_summary}")
        if result.error:
            print(f"error: {result.error[:350]}")
        print(f"answer: {result.answer_preview[:180]!r}")

    REPORT_PATH.write_text(
        json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    passed = sum(1 for r in results if r.passed_outcome)
    print(f"\nRound2 outcome: {passed}/{len(results)} passed")
    print(f"Report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
