"""Run the bounded paid Version 03/04 context-management slice once."""

from __future__ import annotations

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
MODEL = "openai/gpt-5.6-luna"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_REQUESTS = 30
WINDOW = 16_384
FILLER = "Historical implementation detail. " * 1_250


@dataclass
class Result:
    task_id: str
    version: str
    process_pass: bool | None
    outcome_pass: bool
    answer: str
    compactions: int
    requests: int
    error: str | None
    elapsed_seconds: float


class CountedProvider:
    """One OpenRouter provider with a hard authorization boundary."""

    def __init__(self) -> None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        if os.getenv("OPENROUTER_MODEL") != MODEL:
            raise RuntimeError(f"OPENROUTER_MODEL must be exactly {MODEL}")
        self.client = OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            timeout=120.0,
            max_retries=2,
        )
        self.requests: list[dict[str, Any]] = []

    def __call__(
        self,
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
        *,
        max_output_tokens: int | None = None,
    ) -> Any:
        if len(self.requests) >= MAX_REQUESTS:
            raise RuntimeError(f"paid request cap reached ({MAX_REQUESTS})")
        kind = "summary" if not tools and max_output_tokens else "regular"
        record = {
            "number": len(self.requests) + 1,
            "kind": kind,
            "input_items": len(messages),
            "input_tokens": None,
            "output_tokens": None,
        }
        self.requests.append(record)
        print(
            f"request {record['number']}/{MAX_REQUESTS}: {kind} "
            f"({len(messages)} input items)",
            flush=True,
        )
        response = self.client.responses.create(
            model=MODEL,
            instructions=instructions,
            input=messages,
            tools=tools,
            max_output_tokens=max_output_tokens or 1_024,
        )
        usage = getattr(response, "usage", None)
        record["input_tokens"] = getattr(usage, "input_tokens", None)
        record["output_tokens"] = getattr(usage, "output_tokens", None)
        return response


def reset_imports(source: Path) -> None:
    for name in list(sys.modules):
        if name == "coding_kid" or name.startswith("coding_kid."):
            del sys.modules[name]
    sys.path[:] = [entry for entry in sys.path if not entry.endswith("\\src")]
    sys.path.insert(0, str(source))


def workspace(name: str) -> Path:
    root = WORKSPACES.resolve()
    target = (WORKSPACES / name).resolve()
    if target == root or not target.is_relative_to(root):
        raise RuntimeError(f"unsafe workspace path: {target}")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    (target / ".git").mkdir()
    return target


def base_items(task: dict[str, str]) -> list[Any]:
    if task["id"] == "tool-evidence":
        model_round = [
            {
                "type": "function_call",
                "call_id": "evidence-call",
                "name": "read",
                "arguments": '{"path":"evidence.txt"}',
            },
            {
                "type": "function_call_output",
                "call_id": "evidence-call",
                "output": f"EVIDENCE-CEDAR\n{FILLER}",
            },
        ]
    else:
        model_round = [{"role": "assistant", "content": FILLER}]
    return [
        {"role": "user", "content": task["initial"]},
        *model_round,
        {"role": "user", "content": task["latest"]},
    ]


def run_v03(task: dict[str, str], provider: CountedProvider) -> Result:
    started = time.perf_counter()
    first_request = len(provider.requests)
    answer = ""
    error = None
    try:
        reset_imports(ROOT / "versions" / "03-context-assembly" / "src")
        from coding_kid.agent import run_turn
        from coding_kid.context import SessionContext
        from coding_kid.tools import clear_todos

        clear_todos()
        cwd = workspace(f"v03-{task['id']}")
        context = SessionContext.capture(cwd)
        answer = run_turn(
            base_items(task),
            provider,
            session_context=context,
        )
    except Exception as exception:  # noqa: BLE001
        error = (
            f"{type(exception).__name__}: {exception}\n{traceback.format_exc()[-2000:]}"
        )
    return Result(
        task_id=task["id"],
        version="v03",
        process_pass=None,
        outcome_pass=answer.strip() == task["expected"],
        answer=answer,
        compactions=0,
        requests=len(provider.requests) - first_request,
        error=error,
        elapsed_seconds=round(time.perf_counter() - started, 3),
    )


def append_items(state: Any, items: list[Any]) -> None:
    state.append_user(str(items[0]["content"]))
    state.append_model_round(items[1:-1])
    state.append_user(str(items[-1]["content"]))


def run_v04(task: dict[str, str], provider: CountedProvider) -> Result:
    started = time.perf_counter()
    first_request = len(provider.requests)
    answer = ""
    error = None
    process_pass = False
    compactions = 0
    try:
        reset_imports(ROOT / "src")
        from coding_kid.agent import current_instructions, run_turn
        from coding_kid.compaction import compact_context
        from coding_kid.context import SessionContext
        from coding_kid.context_manager import ContextBudget, ContextManager
        from coding_kid.tools import clear_todos, tool_definitions

        clear_todos()
        cwd = workspace(f"v04-{task['id']}")
        context = SessionContext.capture(cwd)
        manager = ContextManager(context, ContextBudget(WINDOW, "evaluation"))
        append_items(manager.conversation, base_items(task))
        tools = tool_definitions()
        instructions = current_instructions(context)
        compact_context(
            manager,
            provider,
            instructions=instructions,
            tools=tools,
            trigger="evaluation",
        )

        expected_compactions = 1
        if task["id"] == "repeated-compaction":
            manager.conversation.append_model_round(
                [{"role": "assistant", "content": FILLER}]
            )
            manager.conversation.append_user(task["latest"])
            compact_context(
                manager,
                provider,
                instructions=instructions,
                tools=tools,
                trigger="evaluation-repeat",
            )
            expected_compactions = 2

        answer = run_turn(manager, provider, session_context=context)
        compactions = len(manager.conversation.checkpoints)
        final_input = manager.model_input()
        rendered = json.dumps(final_input, ensure_ascii=False, default=str)
        threshold = manager.budget.auto_compact_threshold
        process_pass = (
            compactions == expected_compactions
            and "bounded context checkpoint" in rendered
            and task["latest"] in rendered
            and threshold is not None
            and manager.request_estimate(current_instructions(context), tools)
            < threshold
        )
    except Exception as exception:  # noqa: BLE001
        error = (
            f"{type(exception).__name__}: {exception}\n{traceback.format_exc()[-2000:]}"
        )
    return Result(
        task_id=task["id"],
        version="v04",
        process_pass=process_pass,
        outcome_pass=answer.strip() == task["expected"],
        answer=answer,
        compactions=compactions,
        requests=len(provider.requests) - first_request,
        error=error,
        elapsed_seconds=round(time.perf_counter() - started, 3),
    )


def run_cli_smoke(provider: CountedProvider) -> dict[str, Any]:
    started = time.perf_counter()
    first_request = len(provider.requests)
    error = None
    outputs: list[str] = []
    expected = "SMOKE-ALPHA-BRAVO-CHARLIE"
    cwd = workspace("v04-cli-smoke")
    for name, marker in (
        ("evidence-a.txt", "ALPHA"),
        ("evidence-b.txt", "BRAVO"),
        ("evidence-c.txt", "CHARLIE"),
    ):
        (cwd / name).write_text(f"MARKER={marker}\n{FILLER}", encoding="utf-8")
    (cwd / "AGENTS.md").write_text(
        "Use evidence from files. Verify created output before finishing.\n",
        encoding="utf-8",
    )
    prompt = (
        "Read evidence-a.txt, evidence-b.txt, and evidence-c.txt. Then write "
        "result.txt containing exactly SMOKE-ALPHA-BRAVO-CHARLIE, verify its "
        "contents with a shell command, and report completion."
    )
    original_cwd = Path.cwd()
    original_window = os.environ.get("CODING_KID_CONTEXT_WINDOW")
    try:
        reset_imports(ROOT / "src")
        import coding_kid.cli as cli

        original_run_turn = cli.run_turn

        def counted_run_turn(manager: Any, **kwargs: Any) -> str:
            return original_run_turn(manager, provider, **kwargs)

        cli.run_turn = counted_run_turn
        cli.generate = provider
        os.environ["CODING_KID_CONTEXT_WINDOW"] = str(WINDOW)
        os.chdir(cwd)
        answers = iter((prompt, "/exit"))
        cli.chat(
            input_function=lambda _: next(answers),
            output_function=outputs.append,
        )
    except Exception as exception:  # noqa: BLE001
        error = (
            f"{type(exception).__name__}: {exception}\n{traceback.format_exc()[-2000:]}"
        )
    finally:
        os.chdir(original_cwd)
        if original_window is None:
            os.environ.pop("CODING_KID_CONTEXT_WINDOW", None)
        else:
            os.environ["CODING_KID_CONTEXT_WINDOW"] = original_window

    result_path = cwd / "result.txt"
    result = (
        result_path.read_text(encoding="utf-8").strip() if result_path.is_file() else ""
    )
    return {
        "process_pass": any("[context] compacted:" in line for line in outputs),
        "outcome_pass": result == expected,
        "result": result,
        "outputs": outputs,
        "requests": len(provider.requests) - first_request,
        "error": error,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def report(name: str, results: list[Result], provider: CountedProvider) -> None:
    payload = {
        "model": MODEL,
        "request_cap": MAX_REQUESTS,
        "results": [asdict(result) for result in results],
        "request_log": provider.requests,
    }
    (BASE / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_scorecard(
    v03: list[Result],
    v04: list[Result],
    cli_smoke: dict[str, Any],
    request_count: int,
) -> None:
    v03_outcome = sum(result.outcome_pass for result in v03)
    v04_process = sum(bool(result.process_pass) for result in v04)
    v04_outcome = sum(result.outcome_pass for result in v04)
    lines = [
        "# Version 04 Context-Management Scorecard",
        "",
        f"- Model: `{MODEL}`",
        f"- Paid requests: **{request_count} / {MAX_REQUESTS}**",
        f"- Version 03 outcome: **{v03_outcome}/3**",
        f"- Version 04 process: **{v04_process}/3**",
        f"- Version 04 outcome: **{v04_outcome}/3**",
        f"- Version 04 CLI compaction: **{'pass' if cli_smoke['process_pass'] else 'fail'}**",
        f"- Version 04 CLI outcome: **{'pass' if cli_smoke['outcome_pass'] else 'fail'}**",
        "",
        "| Fixture | V03 outcome | V04 process | V04 outcome | Compactions |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for old, new in zip(v03, v04, strict=True):
        lines.append(
            f"| {old.task_id} | {'pass' if old.outcome_pass else 'fail'} | "
            f"{'pass' if new.process_pass else 'fail'} | "
            f"{'pass' if new.outcome_pass else 'fail'} | {new.compactions} |"
        )
    lines.extend(
        [
            "",
            "Completion target: V04 process and outcome 3/3, V04 outcome not below ",
            "V03, and both CLI checks pass within the request cap.",
            "",
        ]
    )
    (BASE / "SCORECARD.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    provider = CountedProvider()
    v03 = [run_v03(task, provider) for task in tasks]
    v04 = [run_v04(task, provider) for task in tasks]
    cli_smoke = run_cli_smoke(provider)
    report("v03_report.json", v03, provider)
    report("v04_report.json", v04, provider)
    (BASE / "cli_smoke_report.json").write_text(
        json.dumps(
            {"model": MODEL, **cli_smoke},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    write_scorecard(v03, v04, cli_smoke, len(provider.requests))
    success = (
        all(result.outcome_pass for result in v03)
        and all(bool(result.process_pass) and result.outcome_pass for result in v04)
        and cli_smoke["process_pass"]
        and cli_smoke["outcome_pass"]
        and len(provider.requests) <= MAX_REQUESTS
    )
    print(f"completed with {len(provider.requests)}/{MAX_REQUESTS} paid requests")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
