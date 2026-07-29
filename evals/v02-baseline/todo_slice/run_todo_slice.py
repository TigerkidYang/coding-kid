"""Run Coding Kid V01 archive or current V02 on the Todo discrimination slice.

Usage:
  uv run python evals/v02-baseline/todo_slice/run_todo_slice.py --agent v01
  uv run python evals/v02-baseline/todo_slice/run_todo_slice.py --agent v02 --only-v01-fails
  uv run python evals/v02-baseline/todo_slice/run_todo_slice.py --write-scorecard
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
FIXTURES = BASE / "fixtures"
WORKSPACES = BASE / "workspaces"
TASKS_PATH = BASE / "tasks.json"
V01_REPORT = BASE / "v01_report.json"
V02_REPORT = BASE / "v02_report.json"
SCORECARD = BASE / "SCORECARD.md"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"


@dataclass
class ProcessStats:
    used_todo: bool = False
    todo_calls: int = 0
    tool_calls: list[str] = field(default_factory=list)
    final_todos: list[dict[str, str]] = field(default_factory=list)
    had_progress: bool = False
    process_pass: bool | None = None


@dataclass
class TaskResult:
    task_id: str
    agent: str
    outcome_pass: bool
    checks: dict[str, Any]
    elapsed_sec: float
    answer_preview: str
    error: str | None = None
    process: ProcessStats | None = None


def load_tasks() -> list[dict[str, Any]]:
    return json.loads(TASKS_PATH.read_text(encoding="utf-8"))


def file_fingerprints(root: Path, rel_paths: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in rel_paths:
        path = root / rel
        if not path.exists():
            out[rel] = ""
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        out[rel] = digest
    return out


def collect_test_files(workspace: Path) -> list[str]:
    files: list[str] = []
    for path in workspace.rglob("test*.py"):
        files.append(str(path.relative_to(workspace)).replace("\\", "/"))
    for path in workspace.rglob("*_test.py"):
        rel = str(path.relative_to(workspace)).replace("\\", "/")
        if rel not in files:
            files.append(rel)
    return sorted(files)


def reset_workspace(task_id: str, fixture: str) -> Path:
    src = FIXTURES / fixture
    dst = WORKSPACES / task_id
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return dst


def run_pytest(workspace: Path, targets: list[str]) -> tuple[bool, str]:
    python = str(VENV_PY if VENV_PY.exists() else sys.executable)
    cmd = [
        python,
        "-m",
        "pytest",
        *targets,
        "-q",
        "--tb=line",
        "-p",
        "no:cacheprovider",
        "--noconftest",
        "-o",
        "addopts=",
        "--rootdir",
        str(workspace),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(workspace)
    proc = subprocess.run(
        cmd,
        cwd=str(workspace),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output[-4000:]


def grade_outcome(workspace: Path, task: dict[str, Any], before_tests: dict[str, str]) -> dict[str, Any]:
    grade = task["grade"]
    checks: dict[str, Any] = {"details": []}
    ok = True

    for rel in grade.get("require_files", []):
        exists = (workspace / rel).exists()
        checks["details"].append({"require_file": rel, "ok": exists})
        ok = ok and exists

    for needle in grade.get("require_readme_mentions", []):
        readme = workspace / "README.md"
        text = readme.read_text(encoding="utf-8") if readme.exists() else ""
        found = needle.lower() in text.lower() if needle.startswith("##") else needle in text
        if needle.startswith("##"):
            found = needle in text
        checks["details"].append({"readme_mentions": needle, "ok": found})
        ok = ok and found

    for rel, needles in grade.get("require_file_mentions", {}).items():
        text = (workspace / rel).read_text(encoding="utf-8") if (workspace / rel).exists() else ""
        for needle in needles:
            found = needle in text
            checks["details"].append({"file_mentions": f"{rel}:{needle}", "ok": found})
            ok = ok and found

    if grade.get("forbid_test_edits"):
        after = file_fingerprints(workspace, list(before_tests))
        unchanged = after == before_tests
        checks["details"].append({"tests_unchanged": True, "ok": unchanged})
        if not unchanged:
            checks["changed_tests"] = {
                rel: {"before": before_tests.get(rel), "after": after.get(rel)}
                for rel in sorted(set(before_tests) | set(after))
                if before_tests.get(rel) != after.get(rel)
            }
        ok = ok and unchanged

    if grade.get("pytest"):
        passed, output = run_pytest(workspace, grade["pytest"])
        checks["details"].append({"pytest": grade["pytest"], "ok": passed})
        checks["pytest_output"] = output
        ok = ok and passed

    checks["outcome_pass"] = ok
    return checks


def score_process(stats: ProcessStats) -> ProcessStats:
    statuses = {item.get("status") for item in stats.final_todos}
    stats.had_progress = ("completed" in statuses) or (
        bool(stats.final_todos) and ("in_progress" in statuses or "pending" in statuses)
    )
    stats.process_pass = bool(
        stats.used_todo and (stats.todo_calls >= 2 or stats.had_progress)
    )
    return stats


def import_agent(agent: str):
    # Ensure only the chosen package is imported.
    for key in list(sys.modules):
        if key == "coding_kid" or key.startswith("coding_kid."):
            del sys.modules[key]

    if agent == "v01":
        src = ROOT / "versions" / "01-minimal-agent" / "src"
    elif agent == "v02":
        src = ROOT / "src"
    else:
        raise ValueError(agent)

    sys.path.insert(0, str(src))
    from coding_kid.agent import run_turn  # type: ignore

    clear_todos = None
    get_todos = None
    if agent == "v02":
        from coding_kid.tools import clear_todos, get_todos  # type: ignore

    return run_turn, clear_todos, get_todos


def run_one(task: dict[str, Any], agent: str) -> TaskResult:
    run_turn, clear_todos, get_todos = import_agent(agent)
    workspace = reset_workspace(task["id"], task["fixture"])
    before_tests = file_fingerprints(workspace, collect_test_files(workspace))

    tool_names: list[str] = []
    todo_calls = 0

    def on_tool(name: str, arguments: dict[str, Any], result: str) -> None:
        nonlocal todo_calls
        tool_names.append(name)
        if name == "todo":
            todo_calls += 1
        preview = json.dumps(arguments, ensure_ascii=False)
        if len(preview) > 160:
            preview = preview[:157] + "..."
        print(f"  [tool] {name} {preview}", flush=True)
        if result.startswith("ERROR:"):
            print(f"  {result[:300]}", flush=True)

    process = ProcessStats()
    answer = ""
    error = None
    started = time.time()
    original = Path.cwd()
    try:
        if clear_todos is not None:
            clear_todos()
        os.chdir(workspace)
        answer = run_turn(
            [{"role": "user", "content": task["goal_only_prompt"]}],
            on_tool=on_tool,
        )
        if get_todos is not None:
            process.final_todos = get_todos()
    except Exception as exc:  # noqa: BLE001
        error = f"{exc}\n{traceback.format_exc()}"
        print(f"  ERROR: {exc}", flush=True)
    finally:
        os.chdir(original)
        if clear_todos is not None:
            clear_todos()

    elapsed = round(time.time() - started, 2)
    checks = grade_outcome(workspace, task, before_tests)
    process.tool_calls = tool_names
    process.todo_calls = todo_calls
    process.used_todo = todo_calls > 0
    if agent == "v02":
        score_process(process)
    else:
        process.process_pass = None

    return TaskResult(
        task_id=task["id"],
        agent=agent,
        outcome_pass=bool(checks["outcome_pass"]),
        checks=checks,
        elapsed_sec=elapsed,
        answer_preview=(answer or "")[:500],
        error=error,
        process=process if agent == "v02" else process,
    )


def save_report(path: Path, agent: str, results: list[TaskResult]) -> None:
    payload = {
        "agent": agent,
        "model": os.getenv("OPENROUTER_MODEL", ""),
        "results": [
            {
                **{k: v for k, v in asdict(r).items() if k != "process"},
                "process": asdict(r.process) if r.process else None,
            }
            for r in results
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {path}")


def v01_fail_ids() -> set[str]:
    if not V01_REPORT.exists():
        raise FileNotFoundError(f"missing {V01_REPORT}; run --agent v01 first")
    data = json.loads(V01_REPORT.read_text(encoding="utf-8"))
    return {
        item["task_id"]
        for item in data["results"]
        if not item.get("outcome_pass")
    }


def write_scorecard() -> None:
    if not V01_REPORT.exists() or not V02_REPORT.exists():
        raise FileNotFoundError("Need both v01_report.json and v02_report.json")

    v01 = json.loads(V01_REPORT.read_text(encoding="utf-8"))
    v02 = json.loads(V02_REPORT.read_text(encoding="utf-8"))
    v01_map = {r["task_id"]: r for r in v01["results"]}
    v02_map = {r["task_id"]: r for r in v02["results"]}
    survivors = sorted(v02_map)

    lines = [
        "# Todo Discrimination Scorecard",
        "",
        f"Model: `{v02.get('model') or v01.get('model') or 'unknown'}`",
        "",
        "Primary evidence for Version 02 Todo. Verified × 10 is not used here.",
        "",
        "## Protocol",
        "",
        "- Goal-only prompts (no numbered step lists in the user message).",
        "- Dual metrics: Outcome (local checks) + Process (todo usage, V02).",
        "- Slice filtered to tasks Version 01 failed on Outcome.",
        "",
        "## Results",
        "",
        "| Task | V01 Outcome | V02 Outcome | V02 Process | V02 todo_calls | Notes |",
        "|------|-------------|-------------|-------------|----------------|-------|",
    ]

    v01_pass = 0
    v02_pass = 0
    process_pass = 0
    for task_id in survivors:
        a = v01_map.get(task_id, {})
        b = v02_map[task_id]
        a_ok = bool(a.get("outcome_pass"))
        b_ok = bool(b.get("outcome_pass"))
        proc = b.get("process") or {}
        p_ok = proc.get("process_pass")
        if a_ok:
            v01_pass += 1
        if b_ok:
            v02_pass += 1
        if p_ok:
            process_pass += 1
        note = ""
        if b.get("error"):
            note = "agent error"
        elif not b_ok:
            failed = [
                d for d in (b.get("checks") or {}).get("details", []) if not d.get("ok")
            ]
            if failed:
                note = json.dumps(failed[0], ensure_ascii=False)[:80]
        lines.append(
            f"| {task_id} | {'PASS' if a_ok else 'FAIL'} | "
            f"{'PASS' if b_ok else 'FAIL'} | "
            f"{'PASS' if p_ok else 'FAIL'} | {proc.get('todo_calls', 0)} | {note} |"
        )

    n = len(survivors)
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Survivor tasks (V01 Outcome fail filter applied for V02 run): **{n}**",
            f"- V01 Outcome on survivors: **{v01_pass}/{n}** (should be 0 if filter held)",
            f"- V02 Outcome on survivors: **{v02_pass}/{n}**",
            f"- V02 Process pass: **{process_pass}/{n}**",
            "",
            "## Verdict rule",
            "",
            "- Todo looks helpful if V02 Outcome >> V01 and Process is high.",
            "- If Outcome stays flat, Todo alone is not enough (budget / other skills).",
            "",
            "## Full-slice V01 gate",
            "",
        ]
    )

    dropped = [tid for tid, row in sorted(v01_map.items()) if row.get("outcome_pass")]
    if dropped:
        lines.append(
            "Dropped after V01 (already Outcome-pass; cannot prove Todo gap): "
            + ", ".join(dropped)
        )
    else:
        lines.append("No tasks dropped; V01 Outcome-failed the full assembled slice.")

    SCORECARD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {SCORECARD}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", choices=["v01", "v02"])
    parser.add_argument("--only-v01-fails", action="store_true")
    parser.add_argument("--task", action="append", default=[])
    parser.add_argument("--write-scorecard", action="store_true")
    args = parser.parse_args()

    if args.write_scorecard and not args.agent:
        write_scorecard()
        return 0

    if not args.agent:
        parser.error("--agent is required unless --write-scorecard")

    if not os.getenv("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is not set", file=sys.stderr)
        return 1

    if not FIXTURES.exists():
        print("Fixtures missing; run bootstrap_fixtures.py first", file=sys.stderr)
        return 1

    tasks = load_tasks()
    if args.task:
        wanted = set(args.task)
        tasks = [t for t in tasks if t["id"] in wanted]
    if args.only_v01_fails:
        fails = v01_fail_ids()
        tasks = [t for t in tasks if t["id"] in fails]
        print(f"Filtered to V01 Outcome failures: {[t['id'] for t in tasks]}")

    results: list[TaskResult] = []
    for task in tasks:
        print(f"=== {args.agent} :: {task['id']} ===", flush=True)
        result = run_one(task, args.agent)
        print(
            f"outcome={'PASS' if result.outcome_pass else 'FAIL'} "
            f"elapsed={result.elapsed_sec}s",
            flush=True,
        )
        results.append(result)

    out = V01_REPORT if args.agent == "v01" else V02_REPORT
    save_report(out, args.agent, results)

    if args.agent == "v02" and V01_REPORT.exists():
        write_scorecard()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
