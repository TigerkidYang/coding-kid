"""Run Coding Kid V01 or V02 on official SWE-bench instance workspaces.

The agent never receives the gold patch or official test patch. File tools run
against a host workspace copied from the official instance image. The execute
tool runs inside that same image with networking disabled, so repository tests
use the official dependencies without allowing network access.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from datasets import load_dataset
from openai import OpenAI

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
WORK_ROOT = BASE / "workspaces"
RESULTS_ROOT = BASE / "results"
DATASET_NAME = "SWE-bench/SWE-bench_Verified"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_CREDITS_URL = f"{OPENROUTER_BASE_URL}/credits"


@dataclass
class ToolEvent:
    name: str
    arguments: dict[str, Any]
    result_preview: str


@dataclass
class InferenceResult:
    instance_id: str
    agent: str
    model: str
    duration_s: float
    answer: str
    model_patch: str
    patch_lines: int
    modified_tests: list[str]
    tool_events: list[ToolEvent] = field(default_factory=list)
    error: str | None = None


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def instance_image(instance_id: str) -> str:
    encoded = instance_id.replace("__", "_1776_")
    return f"swebench/sweb.eval.x86_64.{encoded}:latest"


def load_ids(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = data if isinstance(data, list) else data.get("instance_ids")
    if not isinstance(ids, list) or not ids:
        raise ValueError(f"{path} does not contain instance_ids")
    return ids


def account_usage_usd(api_key: str) -> float | None:
    """Read total billed usage without exposing account or credential details."""
    request = urllib.request.Request(
        OPENROUTER_CREDITS_URL,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        return float(payload["data"]["total_usage"])
    except (OSError, KeyError, TypeError, ValueError, urllib.error.URLError):
        return None


def assert_within_work_root(path: Path) -> Path:
    resolved_root = WORK_ROOT.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root) or resolved == resolved_root:
        raise RuntimeError(f"refusing workspace operation outside {resolved_root}")
    return resolved


def reset_workspace(instance_id: str, image: str) -> Path:
    destination = assert_within_work_root(WORK_ROOT / instance_id)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    extractor = f"ck-extract-{re.sub(r'[^a-zA-Z0-9_.-]', '-', instance_id)}"
    run(["docker", "rm", "-f", extractor], timeout=30)
    created = run(
        [
            "docker",
            "create",
            "--name",
            extractor,
            "--network",
            "none",
            image,
            "true",
        ],
        timeout=60,
    )
    if created.returncode != 0:
        raise RuntimeError(created.stderr or created.stdout)
    try:
        copied = run(
            ["docker", "cp", f"{extractor}:/testbed/.", str(destination)],
            timeout=600,
        )
        if copied.returncode != 0:
            raise RuntimeError(copied.stderr or copied.stdout)
    finally:
        run(["docker", "rm", "-f", extractor], timeout=30)

    if not (destination / ".git").exists():
        raise RuntimeError(f"official image did not contain /testbed/.git: {image}")
    configured = run(
        ["git", "config", "core.filemode", "false"],
        cwd=destination,
        timeout=30,
    )
    if configured.returncode != 0:
        raise RuntimeError(configured.stderr or configured.stdout)
    reset = run(["git", "reset", "--hard", "HEAD"], cwd=destination, timeout=120)
    if reset.returncode != 0:
        raise RuntimeError(reset.stderr or reset.stdout)
    cleaned = run(["git", "clean", "-fdx"], cwd=destination, timeout=120)
    if cleaned.returncode != 0:
        raise RuntimeError(cleaned.stderr or cleaned.stdout)
    return destination


def start_test_container(instance_id: str, image: str, workspace: Path) -> str:
    name = f"ck-run-{re.sub(r'[^a-zA-Z0-9_.-]', '-', instance_id)}"
    run(["docker", "rm", "-f", name], timeout=30)
    mounted = f"type=bind,source={workspace.resolve()},target=/testbed"
    started = run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--network",
            "none",
            "--name",
            name,
            "--mount",
            mounted,
            "--workdir",
            "/testbed",
            "--entrypoint",
            "/bin/bash",
            image,
            "-lc",
            "while true; do sleep 3600; done",
        ],
        timeout=120,
    )
    if started.returncode != 0:
        raise RuntimeError(started.stderr or started.stdout)
    return name


def import_agent(agent: str):
    sources = {
        "v01": ROOT / "versions" / "01-minimal-agent" / "src",
        "v02": ROOT / "versions" / "02-task-decomposition" / "src",
        "v03": ROOT / "src",
    }
    for key in list(sys.modules):
        if key == "coding_kid" or key.startswith("coding_kid."):
            del sys.modules[key]
    source = sources[agent]
    sys.path.insert(0, str(source))
    agent_module = importlib.import_module("coding_kid.agent")
    tools_module = importlib.import_module("coding_kid.tools")
    return agent_module, tools_module


def adapt_prompt_for_linux(agent_module: Any) -> None:
    prompt = agent_module.SYSTEM_PROMPT
    prompt = prompt.replace(
        "The execute tool runs commands through Windows cmd.exe. Use Windows commands.",
        (
            "The execute tool runs commands inside the official Linux SWE-bench "
            "container. Use POSIX shell commands and work in /testbed."
        ),
    )
    prompt = re.sub(
        r"Current working directory: .*\nConfigured model",
        "Current working directory: /testbed\nConfigured model",
        prompt,
    )
    agent_module.SYSTEM_PROMPT = prompt


def docker_execute(container: str, command: str) -> str:
    completed = run(
        ["docker", "exec", container, "bash", "-lc", command],
        timeout=120,
    )
    stdout = completed.stdout.rstrip()
    stderr = completed.stderr.rstrip()
    return f"exit_code: {completed.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"


def strip_mode_only_diffs(patch: str) -> str:
    """Remove Windows bind-mount permission noise from a generated patch."""
    blocks = re.split(r"(?=^diff --git )", patch, flags=re.MULTILINE)
    substantive = [
        block
        for block in blocks
        if not block.startswith("diff --git ")
        or re.search(
            r"^(?:@@|new file mode|deleted file mode|GIT binary patch)",
            block,
            flags=re.MULTILINE,
        )
    ]
    return "".join(substantive)


def capture_patch(workspace: Path) -> tuple[str, list[str]]:
    untracked = run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=workspace,
    )
    for relative in [line for line in untracked.stdout.splitlines() if line.strip()]:
        # POSIX commands occasionally create a literal redirection file such as
        # "NUL". Windows Git cannot add reserved device names, and these shell
        # artifacts are never part of a solution patch.
        if any(
            re.fullmatch(
                r"(?i)(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?",
                part,
            )
            for part in Path(relative).parts
        ):
            continue
        intent = run(["git", "add", "-N", "--", relative], cwd=workspace)
        if intent.returncode != 0:
            raise RuntimeError(intent.stderr or intent.stdout)
    diff = run(["git", "diff", "--binary", "--no-ext-diff"], cwd=workspace)
    if diff.returncode != 0:
        raise RuntimeError(diff.stderr or diff.stdout)
    patch = strip_mode_only_diffs(diff.stdout)

    names = re.findall(r"^diff --git a/(.+?) b/", patch, flags=re.MULTILINE)
    modified_tests = [
        name
        for name in names
        if "/test" in name.lower()
        or name.lower().startswith("test")
        or "/tests/" in name.lower()
    ]
    return patch, modified_tests


def write_outputs(
    report_path: Path,
    predictions_path: Path,
    results: list[InferenceResult],
    run_spend_usd: float,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "dataset": DATASET_NAME,
                "run_spend_usd": round(run_spend_usd, 6),
                "results": [
                    {
                        **asdict(result),
                        "tool_events": [asdict(event) for event in result.tool_events],
                    }
                    for result in results
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    with predictions_path.open("w", encoding="utf-8") as file:
        for result in results:
            file.write(
                json.dumps(
                    {
                        "instance_id": result.instance_id,
                        "model_name_or_path": f"coding-kid-{result.agent}",
                        "model_patch": result.model_patch,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=["v01", "v02", "v03"], required=True)
    parser.add_argument("--ids-file", type=Path, required=True)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument(
        "--run-name",
        default="calibration",
        help="Safe filename prefix for the report and predictions.",
    )
    parser.add_argument(
        "--tool-budget",
        type=int,
        default=64,
        help="High shared safety ceiling for non-todo tool calls.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=80,
        help="High safety ceiling for model/tool loop iterations.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=8192,
        help="Maximum output tokens for each model request.",
    )
    parser.add_argument(
        "--max-spend-usd",
        type=float,
        default=1.5,
        help="Stop before starting another instance once this run spends the limit.",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run_name):
        parser.error("--run-name may contain only letters, digits, '_' and '-'")
    if args.tool_budget < 1:
        parser.error("--tool-budget must be positive")
    if args.max_steps < 1:
        parser.error("--max-steps must be positive")
    if args.max_output_tokens < 1:
        parser.error("--max-output-tokens must be positive")
    if args.max_spend_usd <= 0:
        parser.error("--max-spend-usd must be positive")

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY is not set", file=sys.stderr)
        return 1
    model = os.getenv("OPENROUTER_MODEL", "not set")
    usage_at_start = account_usage_usd(api_key)
    ids = load_ids(args.ids_file)
    if args.only:
        only = set(args.only)
        ids = [instance_id for instance_id in ids if instance_id in only]
    if not ids:
        print("No matching instances", file=sys.stderr)
        return 1

    dataset = {
        row["instance_id"]: dict(row)
        for row in load_dataset(DATASET_NAME, split="test")
        if row["instance_id"] in set(ids)
    }
    missing = set(ids) - set(dataset)
    if missing:
        print(f"Missing dataset instances: {sorted(missing)}", file=sys.stderr)
        return 1

    agent_module, tools_module = import_agent(args.agent)
    adapt_prompt_for_linux(agent_module)
    agent_module.MAX_TOOL_CALLS_PER_TURN = args.tool_budget
    tools_module.TOOLS["execute"]["description"] = (
        "Run one foreground POSIX shell command inside the official Linux "
        "SWE-bench container."
    )
    client = OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        timeout=120.0,
        max_retries=2,
    )

    def call_provider(
        instructions: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
    ) -> Any:
        return client.responses.create(
            model=model,
            instructions=instructions,
            input=messages,
            tools=tools,
            max_output_tokens=args.max_output_tokens,
        )

    clear_todos = getattr(tools_module, "clear_todos", lambda: None)
    get_todos = getattr(tools_module, "get_todos", lambda: [])

    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    report_path = RESULTS_ROOT / f"{args.run_name}_{args.agent}_report.json"
    predictions_path = RESULTS_ROOT / f"{args.run_name}_{args.agent}_predictions.jsonl"
    results: list[InferenceResult] = []
    run_spend_usd = 0.0

    for index, instance_id in enumerate(ids, start=1):
        current_usage = account_usage_usd(api_key)
        if current_usage is not None and usage_at_start is not None:
            run_spend_usd = max(0.0, current_usage - usage_at_start)
        if run_spend_usd >= args.max_spend_usd:
            print(
                f"STOP spend limit reached: ${run_spend_usd:.4f} "
                f">= ${args.max_spend_usd:.4f}",
                flush=True,
            )
            break
        print(
            f"\n===== {index}/{len(ids)} {args.agent} {instance_id} =====", flush=True
        )
        row = dataset[instance_id]
        image = instance_image(instance_id)
        started = time.perf_counter()
        container: str | None = None
        events: list[ToolEvent] = []
        answer = ""
        patch = ""
        modified_tests: list[str] = []
        error: str | None = None
        try:
            if run(["docker", "image", "inspect", image]).returncode != 0:
                raise RuntimeError(f"required local image is missing: {image}")
            workspace = reset_workspace(instance_id, image)
            container = start_test_container(instance_id, image, workspace)
            tools_module.TOOLS["execute"]["function"] = (
                lambda command, active=container: docker_execute(active, command)
            )

            def on_tool(name: str, arguments: dict[str, Any], result: str) -> None:
                safe_arguments = (
                    arguments
                    if name == "todo"
                    else {
                        key: (value[:500] if isinstance(value, str) else value)
                        for key, value in arguments.items()
                        if key != "content"
                    }
                )
                events.append(
                    ToolEvent(
                        name=name,
                        arguments=safe_arguments,
                        result_preview=result[:2000],
                    )
                )
                print(
                    f"[tool] {name} "
                    f"{json.dumps(safe_arguments, ensure_ascii=False)[:700]}",
                    flush=True,
                )

            clear_todos()
            prompt = (
                row["problem_statement"].strip()
                + "\n\n"
                + "Fix the issue in the repository. Do not modify tests. "
                + "Inspect the relevant code, implement the fix, and verify it "
                + "with focused tests when practical."
            )
            original = Path.cwd()
            try:
                os.chdir(workspace)
                messages = [{"role": "user", "content": prompt}]
                run_kwargs: dict[str, Any] = {
                    "max_steps": args.max_steps,
                    "on_tool": on_tool,
                }
                if args.agent == "v03":
                    captured = agent_module.SessionContext.capture(workspace)
                    run_kwargs["session_context"] = replace(
                        captured,
                        cwd=Path("/testbed"),
                        project_root=Path("/testbed"),
                        operating_system="Linux (official SWE-bench container)",
                        shell="bash",
                    )
                answer = agent_module.run_turn(
                    messages,
                    call_provider,
                    **run_kwargs,
                )
            finally:
                os.chdir(original)
            patch, modified_tests = capture_patch(workspace)
            if get_todos():
                print(f"remaining_todos={get_todos()}", flush=True)
        except Exception as exception:
            error = (
                f"{type(exception).__name__}: {exception}\n"
                f"{traceback.format_exc()[-3000:]}"
            )
            print(error, file=sys.stderr, flush=True)
            if "workspace" in locals() and workspace.exists():
                try:
                    patch, modified_tests = capture_patch(workspace)
                except Exception:
                    pass
        finally:
            clear_todos()
            if container:
                run(["docker", "rm", "-f", container], timeout=60)

        result = InferenceResult(
            instance_id=instance_id,
            agent=args.agent,
            model=model,
            duration_s=time.perf_counter() - started,
            answer=answer,
            model_patch=patch,
            patch_lines=len(patch.splitlines()),
            modified_tests=modified_tests,
            tool_events=events,
            error=error,
        )
        results.append(result)
        current_usage = account_usage_usd(api_key)
        if current_usage is not None and usage_at_start is not None:
            run_spend_usd = max(0.0, current_usage - usage_at_start)
        write_outputs(report_path, predictions_path, results, run_spend_usd)
        print(
            f"SAVED patch_lines={result.patch_lines} "
            f"tools={len(events)} error={bool(error)} "
            f"run_spend=${run_spend_usd:.4f}",
            flush=True,
        )

    print(f"Wrote {report_path}", flush=True)
    print(f"Wrote {predictions_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
