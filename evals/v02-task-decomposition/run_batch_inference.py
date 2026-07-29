"""Run one Coding Kid turn across several official SWE-bench workspaces.

This is the feature-specific evaluation for task scheduling and decomposition:
the model receives several independent tasks at once, works in one directory
containing a subdirectory per task, and produces one officially gradable patch
per SWE-bench instance.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any

from datasets import load_dataset
from openai import OpenAI

from run_inference import (
    DATASET_NAME,
    OPENROUTER_BASE_URL,
    RESULTS_ROOT,
    ToolEvent,
    account_usage_usd,
    adapt_prompt_for_linux,
    capture_patch,
    docker_execute,
    import_agent,
    instance_image,
    load_ids,
    run,
)

BASE = Path(__file__).resolve().parent
BATCH_WORK_ROOT = BASE / "batch_workspaces"


def assert_within_batch_root(path: Path) -> Path:
    resolved_root = BATCH_WORK_ROOT.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root) or resolved == resolved_root:
        raise RuntimeError(f"refusing workspace operation outside {resolved_root}")
    return resolved


def reset_batch_workspace(destination: Path, instance_id: str, image: str) -> Path:
    destination = assert_within_batch_root(destination)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    extractor = f"ck-batch-extract-{re.sub(r'[^a-zA-Z0-9_.-]', '-', instance_id)}"
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
    for command in (
        ["git", "config", "core.filemode", "false"],
        ["git", "reset", "--hard", "HEAD"],
        ["git", "clean", "-fdx"],
    ):
        completed = run(command, cwd=destination, timeout=120)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr or completed.stdout)
    return destination


def start_batch_container(
    run_name: str,
    instance_id: str,
    image: str,
    workspace: Path,
) -> str:
    safe_run = re.sub(r"[^a-zA-Z0-9_.-]", "-", run_name)
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]", "-", instance_id)
    name = f"ck-batch-{safe_run}-{safe_id}"[:120]
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


def route_batch_command(command: str, containers: dict[str, str]) -> str:
    """Route `cd <task-directory> && command` to that task's container."""
    match = re.match(
        r"""^\s*cd\s+(?:"([^"]+)"|'([^']+)'|([^\s;&]+))\s*(?:&&|;)\s*(.+)$""",
        command,
        flags=re.DOTALL,
    )
    if not match:
        choices = ", ".join(containers)
        return (
            "exit_code: 2\nstdout:\n\nstderr:\n"
            "Batch execution requires: cd <task-directory> && <command>. "
            f"Choose one of: {choices}"
        )
    directory = next(group for group in match.groups()[:3] if group is not None)
    normalized = directory.replace("\\", "/").removeprefix("./").rstrip("/")
    instance_id = normalized.split("/", 1)[0]
    if instance_id not in containers:
        choices = ", ".join(containers)
        return (
            "exit_code: 2\nstdout:\n\nstderr:\n"
            f"Unknown task directory {instance_id!r}. Choose one of: {choices}"
        )
    inner_command = match.group(4)
    return docker_execute(containers[instance_id], inner_command)


def build_prompt(ids: list[str], dataset: dict[str, dict[str, Any]]) -> str:
    sections = []
    for index, instance_id in enumerate(ids, start=1):
        statement = dataset[instance_id]["problem_statement"].strip()
        sections.append(
            f"## Task {index}: {instance_id}\nDirectory: {instance_id}\n\n{statement}"
        )
    joined = "\n\n".join(sections)
    return (
        "Complete every independent coding task below in this one turn. "
        "Each named directory is a separate official SWE-bench repository. "
        "Do not modify tests. Keep the tasks separate and do not stop after "
        "finishing only some of them.\n\n"
        "For file tools, prefix paths with the task directory. For execute, "
        "always use exactly `cd <task-directory> && <command>` so the command "
        "runs in the correct official Linux container.\n\n"
        f"{joined}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=("v01", "v02"), required=True)
    parser.add_argument("--ids-file", type=Path, required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--tool-budget", type=int, default=240)
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    parser.add_argument("--max-spend-usd", type=float, default=3.0)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run_name):
        parser.error("--run-name may contain only letters, numbers, _ and -")
    if (
        min(
            args.tool_budget,
            args.max_steps,
            args.max_output_tokens,
        )
        < 1
    ):
        parser.error("budgets and limits must be positive")

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY is not set", file=sys.stderr)
        return 1
    model = os.getenv("OPENROUTER_MODEL", "not set")
    ids = load_ids(args.ids_file)
    raw_dataset = load_dataset(DATASET_NAME, split="test")
    dataset = {
        row["instance_id"]: dict(row)
        for row in raw_dataset
        if row["instance_id"] in ids
    }
    missing = set(ids) - set(dataset)
    if missing:
        raise RuntimeError(f"missing dataset instances: {sorted(missing)}")

    agent_module, tools_module = import_agent(args.agent)
    adapt_prompt_for_linux(agent_module)
    agent_module.SYSTEM_PROMPT = agent_module.SYSTEM_PROMPT.replace(
        "Current working directory: /testbed",
        "Current working directory: the batch directory described by the user",
    )
    agent_module.MAX_TOOL_CALLS_PER_TURN = args.tool_budget
    tools_module.TOOLS["execute"]["description"] = (
        "Run one foreground command in a selected official Linux task container. "
        "The command must start with: cd <task-directory> &&"
    )
    clear_todos = getattr(tools_module, "clear_todos", lambda: None)
    get_todos = getattr(tools_module, "get_todos", lambda: [])

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

    batch_root = assert_within_batch_root(BATCH_WORK_ROOT / args.run_name)
    if batch_root.exists():
        shutil.rmtree(batch_root)
    batch_root.mkdir(parents=True)
    containers: dict[str, str] = {}
    workspaces: dict[str, Path] = {}
    events: list[ToolEvent] = []
    error: str | None = None
    answer = ""
    usage_at_start = account_usage_usd(api_key)
    started = time.perf_counter()

    try:
        for instance_id in ids:
            image = instance_image(instance_id)
            if run(["docker", "image", "inspect", image]).returncode != 0:
                raise RuntimeError(f"required local image is missing: {image}")
            workspace = reset_batch_workspace(
                batch_root / instance_id,
                instance_id,
                image,
            )
            workspaces[instance_id] = workspace
            containers[instance_id] = start_batch_container(
                args.run_name,
                instance_id,
                image,
                workspace,
            )

        tools_module.TOOLS["execute"]["function"] = lambda command: route_batch_command(
            command, containers
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
                f"[tool] {name} {json.dumps(safe_arguments, ensure_ascii=False)[:700]}",
                flush=True,
            )

        clear_todos()
        original = Path.cwd()
        try:
            os.chdir(batch_root)
            messages = [{"role": "user", "content": build_prompt(ids, dataset)}]
            answer = agent_module.run_turn(
                messages,
                call_provider,
                max_steps=args.max_steps,
                on_tool=on_tool,
            )
        finally:
            os.chdir(original)
    except Exception as exception:
        error = (
            f"{type(exception).__name__}: {exception}\n{traceback.format_exc()[-4000:]}"
        )
        print(error, file=sys.stderr, flush=True)
    finally:
        remaining_todos = get_todos()
        clear_todos()
        for container in containers.values():
            run(["docker", "rm", "-f", container], timeout=60)

    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    predictions_path = RESULTS_ROOT / f"{args.run_name}_{args.agent}_predictions.jsonl"
    report_path = RESULTS_ROOT / f"{args.run_name}_{args.agent}_report.json"
    predictions = []
    patch_summaries = []
    for instance_id in ids:
        workspace = workspaces.get(instance_id)
        patch = ""
        modified_tests: list[str] = []
        patch_error: str | None = None
        if workspace is not None:
            try:
                patch, modified_tests = capture_patch(workspace)
            except Exception as exception:
                patch_error = f"{type(exception).__name__}: {exception}"
        predictions.append(
            {
                "instance_id": instance_id,
                "model_name_or_path": (f"coding-kid-{args.agent}-batch-{model}"),
                "model_patch": patch,
            }
        )
        patch_summaries.append(
            {
                "instance_id": instance_id,
                "patch_lines": len(patch.splitlines()),
                "modified_tests": modified_tests,
                "error": patch_error,
            }
        )

    predictions_path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in predictions) + "\n",
        encoding="utf-8",
    )
    usage_at_end = account_usage_usd(api_key)
    spend = (
        max(0.0, usage_at_end - usage_at_start)
        if usage_at_start is not None and usage_at_end is not None
        else None
    )
    if spend is not None and spend > args.max_spend_usd:
        error = (
            f"{error or ''}\nBatch spend ${spend:.4f} exceeded "
            f"the ${args.max_spend_usd:.4f} safety threshold."
        ).strip()
    report_path.write_text(
        json.dumps(
            {
                "dataset": DATASET_NAME,
                "agent": args.agent,
                "model": model,
                "instance_ids": ids,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "run_spend_usd": None if spend is None else round(spend, 6),
                "answer": answer,
                "remaining_todos": remaining_todos,
                "patches": patch_summaries,
                "tool_events": [asdict(event) for event in events],
                "error": error,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {report_path}")
    print(f"Wrote {predictions_path}")
    return 1 if error else 0


if __name__ == "__main__":
    raise SystemExit(main())
