from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_scheduler() -> ModuleType:
    path = (
        Path(__file__).parents[1]
        / "evals"
        / "terminal-bench-2-1"
        / "cloudflare-runner"
        / "scheduler.py"
    )
    spec = importlib.util.spec_from_file_location("terminal_bench_scheduler", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def outer_agent_timeout_status(*, traceback: str) -> dict[str, object]:
    return {
        "agent_log_tail": "Coding Kid is ready.\n[tool] task wait task_123",
        "trial_diagnostics": [
            {
                "exception_info": {
                    "exception_type": "RuntimeError",
                    "exception_message": "Command timed out after 1800 seconds",
                    "exception_traceback": traceback,
                },
                "agent_info": {"version": "v16-explicit-maintenance-fix4"},
            }
        ],
    }


def test_outer_installed_agent_timeout_is_a_benchmark_outcome() -> None:
    scheduler = load_scheduler()
    status = outer_agent_timeout_status(
        traceback="trial._run_agent_phase -> installed.exec_as_agent"
    )

    assert scheduler.benchmark_agent_failure(status) is True


def test_runner_setup_timeout_remains_infrastructure() -> None:
    scheduler = load_scheduler()
    status = outer_agent_timeout_status(
        traceback="docker._run_docker_compose_command -> create_environment"
    )

    assert scheduler.benchmark_agent_failure(status) is False
