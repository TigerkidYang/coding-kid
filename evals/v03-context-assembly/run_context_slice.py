"""Run the paired Version 02/03 project-context capability slice."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
TASKS_PATH = BASE / "tasks.json"
WORKSPACES = BASE / "workspaces"
V02_REPORT = BASE / "v02_report.json"
V03_REPORT = BASE / "v03_report.json"
SCORECARD = BASE / "SCORECARD.md"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_PROMPT = (
    "Create result.txt for this project so it follows the conventions that "
    "apply to the current directory, then report what you created."
)


@dataclass
class TaskResult:
    task_id: str
    agent: str
    process_pass: bool | None
    outcome_pass: bool
    result_text: str
    tool_calls: list[str]
    answer_preview: str
    elapsed_seconds: float
    error: str | None


def load_tasks() -> list[dict[str, Any]]:
    return json.loads(TASKS_PATH.read_text(encoding="utf-8"))


def workspace_path(task_id: str) -> Path:
    root = WORKSPACES.resolve()
    path = (WORKSPACES / task_id).resolve()
    if not path.is_relative_to(root) or path == root:
        raise RuntimeError(f"unsafe workspace path: {path}")
    return path


def reset_workspace(task: dict[str, Any]) -> tuple[Path, Path]:
    workspace = workspace_path(task["id"])
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    for relative, content in task["files"].items():
        destination = workspace / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")

    pad_file = task.get("pad_file")
    if pad_file:
        path = workspace / pad_file
        data = path.read_bytes()
        target = int(task["pad_to_bytes"])
        if len(data) > target:
            raise RuntimeError(f"pad source exceeds target: {path}")
        path.write_bytes(data + b"#" * (target - len(data)))

    git_root = workspace / task["git_root"]
    (git_root / ".git").mkdir(parents=True)
    cwd = workspace / task["cwd"]
    cwd.mkdir(parents=True, exist_ok=True)
    return workspace, cwd


def import_agent(agent: str):
    for key in list(sys.modules):
        if key == "coding_kid" or key.startswith("coding_kid."):
            del sys.modules[key]

    src = (
        ROOT / "versions" / "02-task-decomposition" / "src"
        if agent == "v02"
        else ROOT / "src"
    )
    sys.path.insert(0, str(src))
    from coding_kid.agent import run_turn  # type: ignore
    from coding_kid.tools import clear_todos  # type: ignore

    return run_turn, clear_todos


def context_process_pass(
    task: dict[str, Any],
    workspace: Path,
    first_model_input: list[Any],
) -> bool:
    expected_sources = [
        str((workspace / relative).resolve()) for relative in task["expected_sources"]
    ]
    forbidden_sources = [
        str((workspace / relative).resolve()) for relative in task["forbidden_sources"]
    ]

    if not expected_sources:
        if not first_model_input:
            return False
        first = first_model_input[0]
        return first == {
            "role": "user",
            "content": task.get("prompt", DEFAULT_PROMPT),
        }

    if not first_model_input:
        return False
    first = first_model_input[0]
    if not isinstance(first, dict) or first.get("role") != "user":
        return False
    content = str(first.get("content", ""))
    sources_ok = all(source in content for source in expected_sources)
    forbidden_ok = all(source not in content for source in forbidden_sources)
    marker_ok = not task.get("expect_truncation_marker") or (
        "omitted because the shared" in content
    )
    return sources_ok and forbidden_ok and marker_ok


def run_one(
    task: dict[str, Any],
    agent: str,
    client: OpenAI,
    model: str,
) -> TaskResult:
    workspace, cwd = reset_workspace(task)
    original = Path.cwd()
    tool_calls: list[str] = []
    provider_inputs: list[list[Any]] = []
    answer = ""
    error = None
    started = time.perf_counter()

    try:
        os.chdir(cwd)
        run_turn, clear_todos = import_agent(agent)
        clear_todos()

        def provider(
            instructions: str,
            messages: list[Any],
            tools: list[dict[str, Any]],
        ) -> Any:
            provider_inputs.append(list(messages))
            return client.responses.create(
                model=model,
                instructions=instructions,
                input=messages,
                tools=tools,
                max_output_tokens=2048,
            )

        def on_tool(name: str, arguments: dict[str, Any], result: str) -> None:
            tool_calls.append(name)
            preview = json.dumps(arguments, ensure_ascii=False)
            print(f"  [tool] {name} {preview[:180]}", flush=True)
            if result.startswith("ERROR:"):
                print(f"  {result[:300]}", flush=True)

        prompt = task.get("prompt", DEFAULT_PROMPT)
        answer = run_turn(
            [{"role": "user", "content": prompt}],
            provider,
            on_tool=on_tool,
        )
    except Exception as exception:  # noqa: BLE001
        error = (
            f"{type(exception).__name__}: {exception}\n{traceback.format_exc()[-3000:]}"
        )
    finally:
        os.chdir(original)

    result_path = cwd / "result.txt"
    result_text = (
        result_path.read_text(encoding="utf-8", errors="replace").strip()
        if result_path.is_file()
        else ""
    )
    process_pass = (
        context_process_pass(task, workspace, provider_inputs[0])
        if agent == "v03" and provider_inputs
        else None
    )
    return TaskResult(
        task_id=task["id"],
        agent=agent,
        process_pass=process_pass,
        outcome_pass=result_text == task["expected"],
        result_text=result_text,
        tool_calls=tool_calls,
        answer_preview=answer[:500],
        elapsed_seconds=round(time.perf_counter() - started, 3),
        error=error,
    )


def write_scorecard() -> None:
    if not V02_REPORT.exists() or not V03_REPORT.exists():
        raise FileNotFoundError("Run both v02 and v03 before writing the scorecard")
    v02 = json.loads(V02_REPORT.read_text(encoding="utf-8"))
    v03 = json.loads(V03_REPORT.read_text(encoding="utf-8"))
    v02_map = {item["task_id"]: item for item in v02["results"]}
    v03_map = {item["task_id"]: item for item in v03["results"]}

    lines = [
        "# Version 03 Context Assembly Scorecard",
        "",
        f"Model: `{v03['model']}`",
        "",
        "| Task | V02 Outcome | V03 Process | V03 Outcome |",
        "|------|-------------|-------------|-------------|",
    ]
    for task_id in sorted(v03_map):
        old = v02_map[task_id]
        new = v03_map[task_id]
        lines.append(
            f"| {task_id} | {'PASS' if old['outcome_pass'] else 'FAIL'} | "
            f"{'PASS' if new['process_pass'] else 'FAIL'} | "
            f"{'PASS' if new['outcome_pass'] else 'FAIL'} |"
        )

    total = len(v03_map)
    v02_outcomes = sum(bool(item["outcome_pass"]) for item in v02_map.values())
    v03_process = sum(bool(item["process_pass"]) for item in v03_map.values())
    v03_outcomes = sum(bool(item["outcome_pass"]) for item in v03_map.values())
    completion_pass = (
        v03_process == total and v03_outcomes >= 5 and v03_outcomes > v02_outcomes
    )
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- V02 Outcome: **{v02_outcomes}/{total}**",
            f"- V03 Process: **{v03_process}/{total}**",
            f"- V03 Outcome: **{v03_outcomes}/{total}**",
            f"- Completion bar: **{'PASS' if completion_pass else 'FAIL'}**",
            "",
        ]
    )
    SCORECARD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {SCORECARD}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=("v02", "v03"))
    parser.add_argument("--task", action="append", default=[])
    parser.add_argument("--write-scorecard", action="store_true")
    args = parser.parse_args()

    if args.write_scorecard:
        write_scorecard()
        return 0
    if not args.agent:
        parser.error("--agent is required")

    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL")
    if not api_key or not model:
        print("OPENROUTER_API_KEY and OPENROUTER_MODEL are required", file=sys.stderr)
        return 1

    tasks = load_tasks()
    if args.task:
        selected = set(args.task)
        tasks = [task for task in tasks if task["id"] in selected]
    client = OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        timeout=120.0,
        max_retries=2,
    )
    results = []
    for task in tasks:
        print(f"=== {args.agent} :: {task['id']} ===", flush=True)
        result = run_one(task, args.agent, client, model)
        results.append(result)
        print(
            f"  process={result.process_pass} outcome={result.outcome_pass} "
            f"result={result.result_text!r}",
            flush=True,
        )

    report_path = V02_REPORT if args.agent == "v02" else V03_REPORT
    report_path.write_text(
        json.dumps(
            {
                "agent": args.agent,
                "model": model,
                "results": [asdict(result) for result in results],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {report_path}")
    return 1 if any(result.error for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
