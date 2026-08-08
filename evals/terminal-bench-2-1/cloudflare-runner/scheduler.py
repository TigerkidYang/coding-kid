"""Resumable adaptive scheduler for the Cloudflare Terminal-Bench run."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "build-context" / "dataset"
RUN_ID = os.environ.get(
    "CODING_KID_BENCH_RUN_ID", "terminal-bench-2.1-k1-luna-max-shellfix"
)
if not RUN_ID or Path(RUN_ID).name != RUN_ID:
    raise ValueError("CODING_KID_BENCH_RUN_ID must be one directory name")
RUN_DIR = ROOT / "runs" / RUN_ID
STATE_PATH = RUN_DIR / "state.json"
EVENTS_PATH = RUN_DIR / "events.jsonl"
BASE = "https://coding-kid-terminal-bench-runner.runchangyang.workers.dev"
HOST = "coding-kid-terminal-bench-runner.runchangyang.workers.dev"
RESOLVE = f"{HOST}:443:104.21.77.50"
MODEL_URL = os.environ.get(
    "CODING_KID_BENCH_MODEL_URL",
    "https://alien-nat-office-sir.trycloudflare.com/v1/models",
)
POLL_SECONDS = 30
MAX_ATTEMPTS = 5
MAX_CONCURRENCY = int(os.environ.get("CODING_KID_BENCH_MAX_CONCURRENCY", "16"))
if not 1 <= MAX_CONCURRENCY <= 16:
    raise ValueError("CODING_KID_BENCH_MAX_CONCURRENCY must be between 1 and 16")
INITIAL_CONCURRENCY = int(os.environ.get("CODING_KID_BENCH_INITIAL_CONCURRENCY", "4"))
if not 1 <= INITIAL_CONCURRENCY <= MAX_CONCURRENCY:
    raise ValueError(
        "CODING_KID_BENCH_INITIAL_CONCURRENCY must be between 1 and the maximum"
    )
TRIAL_PREFIX = os.environ.get("CODING_KID_BENCH_TRIAL_PREFIX", "k1sf2")
if (
    not TRIAL_PREFIX
    or len(TRIAL_PREFIX) > 16
    or not TRIAL_PREFIX.replace("-", "").isalnum()
):
    raise ValueError(
        "CODING_KID_BENCH_TRIAL_PREFIX must be 1-16 letters, digits, or hyphens"
    )
USE_BOOTSTRAP = os.environ.get("CODING_KID_BENCH_USE_BOOTSTRAP", "1") == "1"

BOOTSTRAP = {
    "openssl-selfsigned-cert": "k1-openssl-cert-shellfix",
    "regex-log": "k1-regex-log-shellfix",
    "count-dataset-tokens": "k1-count-tokens-shellfix",
    "git-multibranch": "k1-git-multibranch-shellfix",
}

# Starts that Cloudflare accepted just before the previous scheduler process
# was stopped, before its next atomic state save completed.
INTERRUPTED_STARTS = {
    "install-windows-3.11": ("k1sf2-install-windows-3-11-3fa532b7", 1),
    "qemu-startup": ("k1sf2-qemu-startup-f8b1a93d-r2", 2),
    "query-optimize": ("k1sf2-query-optimize-717bd87f", 1),
}

HARNESS_REPAIR_TASKS = {
    "adaptive-rejection-sampler",
    "compile-compcert",
    "fix-git",
    "install-windows-3.11",
    "mteb-leaderboard",
    "mteb-retrieve",
    "prove-plus-comm",
    "qemu-alpine-ssh",
    "qemu-startup",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(event: str, **values: Any) -> None:
    record = {"at": now(), "event": event, **values}
    print(json.dumps(record, ensure_ascii=False), flush=True)
    with EVENTS_PATH.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def curl_json(path: str, *, body: dict[str, str] | None = None) -> dict[str, Any]:
    token = os.environ["CODING_KID_BENCH_API_KEY"]
    command = [
        "curl.exe",
        "-sS",
        "--fail-with-body",
        "--max-time",
        "120",
        "--resolve",
        RESOLVE,
        "-H",
        f"Authorization: Bearer {token}",
    ]
    if body is not None:
        command.extend(
            [
                "-H",
                "Content-Type: application/json",
                "-X",
                "POST",
                "--data",
                json.dumps(body, separators=(",", ":")),
            ]
        )
    command.append(f"{BASE}{path}")
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=135,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return json.loads(completed.stdout)


def model_healthy() -> bool:
    token = os.environ["CODING_KID_BENCH_API_KEY"]
    completed = subprocess.run(
        [
            "curl.exe",
            "-sS",
            "--fail",
            "--max-time",
            "20",
            "-H",
            f"Authorization: Bearer {token}",
            MODEL_URL,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=25,
    )
    return completed.returncode == 0 and "gpt-5.6-luna" in completed.stdout


def trial_id(task: str, attempt: int) -> str:
    digest = hashlib.sha256(task.encode()).hexdigest()[:8]
    suffix = "" if attempt == 1 else f"-r{attempt}"
    slug = "".join(character if character.isalnum() else "-" for character in task)
    prefix = slug[: 63 - len(TRIAL_PREFIX) - 2 - len(digest) - len(suffix)]
    return f"{TRIAL_PREFIX}-{prefix}-{digest}{suffix}"


def initial_state(tasks: list[str]) -> dict[str, Any]:
    return {
        "created_at": now(),
        "target_concurrency": INITIAL_CONCURRENCY,
        "last_ramp_at": time.time(),
        "last_backoff_at": 0.0,
        "tasks": {task: {"phase": "pending", "attempt": 0} for task in tasks},
    }


def load_state(tasks: list[str]) -> dict[str, Any]:
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        for task in tasks:
            state["tasks"].setdefault(task, {"phase": "pending", "attempt": 0})
        return state
    return initial_state(tasks)


def save(state: dict[str, Any]) -> None:
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for attempt in range(20):
        try:
            temporary.replace(STATE_PATH)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def claim_scheduler() -> Path:
    """Claim this run directory and expose the real scheduler process ID."""
    pid_path = RUN_DIR / "scheduler.pid"
    for claim_attempt in range(2):
        try:
            descriptor = os.open(pid_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            break
        except FileExistsError as error:
            existing = pid_path.read_text(encoding="ascii", errors="ignore").strip()
            try:
                existing_pid = int(existing)
                os.kill(existing_pid, 0)
            except (OSError, ValueError):
                if claim_attempt == 0:
                    pid_path.unlink(missing_ok=True)
                    continue
            raise RuntimeError(
                f"scheduler ownership already exists for {RUN_ID}: "
                f"pid={existing or 'unknown'}"
            ) from error
    else:  # pragma: no cover - the loop either claims or raises
        raise RuntimeError(f"unable to claim scheduler ownership for {RUN_ID}")
    with os.fdopen(descriptor, "w", encoding="ascii") as stream:
        stream.write(str(os.getpid()))
        stream.flush()
        os.fsync(stream.fileno())
    return pid_path


def release_scheduler(pid_path: Path) -> None:
    try:
        if pid_path.read_text(encoding="ascii").strip() == str(os.getpid()):
            pid_path.unlink()
    except FileNotFoundError:
        pass


def reward(status: dict[str, Any]) -> float | None:
    result = status.get("result")
    if not isinstance(result, dict):
        return None
    stats = result.get("stats")
    if isinstance(stats, dict):
        for key in ("mean_reward", "mean", "reward"):
            value = stats.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    diagnostics = status.get("trial_diagnostics")
    if isinstance(diagnostics, list):
        values: list[float] = []
        for item in diagnostics:
            verifier = item.get("verifier_result") if isinstance(item, dict) else None
            if isinstance(verifier, dict):
                rewards = verifier.get("rewards")
                if isinstance(rewards, dict):
                    values.extend(
                        float(value)
                        for value in rewards.values()
                        if isinstance(value, (int, float))
                    )
        if values:
            return sum(values) / len(values)
    return None


def model_transport_failure(status: dict[str, Any]) -> bool:
    """Detect a model request that failed outside the benchmark task itself."""
    if reward(status) not in {None, 0.0}:
        return False
    log = str(status.get("agent_log_tail") or "")
    transport_markers = (
        "origin_response_timeout",
        "cloudflare_error': True",
        "APITimeoutError",
        "APIConnectionError",
        "Error code: 429",
        "Error code: 500",
        "Error code: 502",
        "Error code: 503",
        "Error code: 504",
        "Error code: 520",
        "Error code: 522",
        "Error code: 524",
        "ProviderProtocolError",
        "Provider returned a null collection",
        "Provider returned no streaming response object",
        "Error: 'NoneType' object is not iterable",
    )
    return any(marker in log for marker in transport_markers)


def benchmark_agent_failure(status: dict[str, Any]) -> bool:
    """Return true for an agent failure that is itself a benchmark outcome."""
    if model_transport_failure(status):
        return False
    diagnostics = status.get("trial_diagnostics")
    if not isinstance(diagnostics, list):
        return False
    for item in diagnostics:
        exception = item.get("exception_info") if isinstance(item, dict) else None
        if not isinstance(exception, dict):
            continue
        if exception.get("exception_type") == "AgentTimeoutError":
            return True
        if (
            exception.get("exception_type") == "NonZeroAgentExitCodeError"
            and status.get("agent_log_tail")
            and isinstance(item.get("agent_info"), dict)
            and item["agent_info"].get("version") not in {None, "unknown"}
        ):
            return True
    return False


def start_task(task: str, entry: dict[str, Any], state: dict[str, Any]) -> None:
    attempt = int(entry.get("attempt", 0)) + 1
    identifier = (
        BOOTSTRAP.get(task)
        if USE_BOOTSTRAP and attempt == 1 and task in BOOTSTRAP
        else trial_id(task, attempt)
    )
    assert identifier is not None
    curl_json(f"/trials/{identifier}/start", body={"task": task})
    entry.update(
        phase="running",
        attempt=attempt,
        trial_id=identifier,
        started_at=now(),
        started_epoch=time.time(),
        container_stopped=False,
    )
    save(state)
    emit("started", task=task, trial_id=identifier, attempt=attempt)


def stop_trial(task: str, entry: dict[str, Any]) -> None:
    if entry.get("container_stopped") or not entry.get("trial_id"):
        return
    try:
        curl_json(f"/trials/{entry['trial_id']}/stop", body={})
        entry["container_stopped"] = True
        emit("container_stopped", task=task, trial_id=entry["trial_id"])
    except Exception as error:
        emit("stop_request_error", task=task, error=str(error)[:500])


def main() -> int:
    if not os.environ.get("CODING_KID_BENCH_API_KEY"):
        print("CODING_KID_BENCH_API_KEY is required", file=sys.stderr)
        return 2
    tasks = sorted(path.name for path in DATASET.iterdir() if path.is_dir())
    if len(tasks) != 89:
        raise RuntimeError(f"expected 89 tasks, found {len(tasks)}")
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state(tasks)
    pause_starts = os.environ.get("CODING_KID_BENCH_PAUSE_STARTS") == "1"
    deferred_tasks = {
        task.strip()
        for task in os.environ.get("CODING_KID_BENCH_DEFER_TASKS", "").split(",")
        if task.strip()
    }
    for task in deferred_tasks:
        entry = state["tasks"].get(task)
        if entry and entry["phase"] == "running":
            entry["phase"] = "retry_pending"
            emit("running_task_deferred", task=task, attempt=entry.get("attempt"))
    if os.environ.get("CODING_KID_BENCH_RESET_STALE_RUNNING") == "1":
        for task, entry in state["tasks"].items():
            if entry["phase"] == "running":
                entry.clear()
                entry.update(phase="pending", attempt=0)
                emit("stale_running_reset", task=task)
    if os.environ.get("CODING_KID_BENCH_ADOPT_INTERRUPTED") == "1":
        for task, (identifier, attempt) in INTERRUPTED_STARTS.items():
            entry = state["tasks"][task]
            if entry["phase"] in {"pending", "retry_pending", "deferred_runner_update"}:
                entry.update(
                    phase="running",
                    attempt=attempt,
                    trial_id=identifier,
                    started_at=now(),
                    started_epoch=time.time() - 180,
                    container_stopped=False,
                )
                emit("interrupted_start_adopted", task=task, trial_id=identifier)
    if os.environ.get("CODING_KID_BENCH_RESET_HARNESS_REPAIRS") == "1":
        for task in HARNESS_REPAIR_TASKS:
            entry = state["tasks"][task]
            if entry["phase"] not in {"running", "completed"}:
                entry.clear()
                entry.update(phase="pending", attempt=0)
                emit("harness_repair_reset", task=task)
    forced_concurrency = os.environ.get("CODING_KID_BENCH_FORCE_CONCURRENCY")
    if forced_concurrency:
        state["target_concurrency"] = max(
            1, min(MAX_CONCURRENCY, int(forced_concurrency))
        )
        state["last_ramp_at"] = time.time()
        state["last_backoff_at"] = time.time()

    for task, entry in state["tasks"].items():
        if entry["phase"] != "completed" and benchmark_agent_failure(
            entry.get("last_error", {})
        ):
            status = entry["last_error"]
            entry.update(
                phase="completed",
                finished_at=now(),
                reward=reward(status) or 0.0,
                status=status,
            )
            emit("agent_timeout_counted", task=task, attempt=entry["attempt"])
        if entry["phase"] == "completed" and model_transport_failure(
            entry.get("status", {})
        ):
            entry["last_error"] = entry.get("status")
            entry.pop("reward", None)
            entry["phase"] = (
                "retry_pending"
                if int(entry.get("attempt", 0)) < MAX_ATTEMPTS
                else "failed_infrastructure"
            )
            emit("model_transport_reclassified", task=task, attempt=entry["attempt"])
        if entry["phase"] in {"completed", "failed_infrastructure"}:
            stop_trial(task, entry)

    # Adopt the four trials launched immediately before this scheduler started.
    if USE_BOOTSTRAP:
        for task, identifier in BOOTSTRAP.items():
            entry = state["tasks"][task]
            if entry["phase"] == "pending":
                entry.update(
                    phase="running",
                    attempt=1,
                    trial_id=identifier,
                    started_at=now(),
                    started_epoch=time.time() - 60,
                )
    save(state)
    emit("scheduler_started", tasks=len(tasks), concurrency=state["target_concurrency"])

    consecutive_request_errors = 0
    while True:
        infrastructure_errors = 0
        for task, entry in state["tasks"].items():
            if entry["phase"] != "running":
                continue
            try:
                status = curl_json(f"/trials/{entry['trial_id']}/status")
                consecutive_request_errors = 0
            except Exception as error:
                consecutive_request_errors += 1
                emit("status_request_error", task=task, error=str(error)[:500])
                continue
            phase = status.get("phase")
            if phase == "completed":
                if model_transport_failure(status):
                    infrastructure_errors += 1
                    entry["last_error"] = status
                    if entry["attempt"] < MAX_ATTEMPTS:
                        entry["phase"] = "retry_pending"
                        emit(
                            "model_transport_retry", task=task, attempt=entry["attempt"]
                        )
                    else:
                        entry.update(
                            phase="failed_infrastructure",
                            finished_at=now(),
                            status=status,
                        )
                        emit("model_transport_exhausted", task=task)
                    save(state)
                    stop_trial(task, entry)
                    continue
                entry.update(
                    phase="completed",
                    finished_at=now(),
                    reward=reward(status),
                    status=status,
                )
                save(state)
                emit("completed", task=task, reward=entry["reward"])
                stop_trial(task, entry)
            elif phase == "infrastructure_error":
                if benchmark_agent_failure(status):
                    entry.update(
                        phase="completed",
                        finished_at=now(),
                        reward=reward(status) or 0.0,
                        status=status,
                    )
                    save(state)
                    emit("agent_timeout_counted", task=task, attempt=entry["attempt"])
                    stop_trial(task, entry)
                    continue
                infrastructure_errors += 1
                entry["last_error"] = status
                if entry["attempt"] < MAX_ATTEMPTS:
                    entry["phase"] = "retry_pending"
                    emit("infrastructure_retry", task=task, attempt=entry["attempt"])
                else:
                    entry.update(
                        phase="failed_infrastructure", finished_at=now(), status=status
                    )
                    emit("infrastructure_exhausted", task=task)
                save(state)
                stop_trial(task, entry)
            elif phase == "idle" and time.time() - entry.get("started_epoch", 0) > 180:
                # A platform replacement can erase ephemeral container state.
                entry["phase"] = "retry_pending"
                save(state)
                emit("container_state_lost", task=task, attempt=entry["attempt"])
                stop_trial(task, entry)

        if infrastructure_errors:
            state["last_backoff_at"] = time.time()
        if not forced_concurrency and (
            infrastructure_errors >= 2 or consecutive_request_errors >= 3
        ):
            old = int(state["target_concurrency"])
            state["target_concurrency"] = max(4, old - 4)
            state["last_backoff_at"] = time.time()
            if state["target_concurrency"] != old:
                emit("concurrency_backoff", old=old, new=state["target_concurrency"])
        elif (
            time.time() - float(state.get("last_ramp_at", 0)) >= 300
            and time.time() - float(state.get("last_backoff_at", 0)) >= 600
            and int(state["target_concurrency"]) < MAX_CONCURRENCY
        ):
            old = int(state["target_concurrency"])
            state["target_concurrency"] = min(MAX_CONCURRENCY, old + 4)
            state["last_ramp_at"] = time.time()
            emit("concurrency_ramp", old=old, new=state["target_concurrency"])

        completed = sum(
            entry["phase"] == "completed" for entry in state["tasks"].values()
        )
        exhausted = sum(
            entry["phase"] == "failed_infrastructure"
            for entry in state["tasks"].values()
        )
        running = sum(entry["phase"] == "running" for entry in state["tasks"].values())
        if completed + exhausted == len(tasks):
            state["finished_at"] = now()
            save(state)
            emit(
                "scheduler_finished",
                completed=completed,
                infrastructure_failed=exhausted,
            )
            return 0 if exhausted == 0 else 1

        healthy = not pause_starts and model_healthy()
        if pause_starts:
            emit("starts_paused", running=running)
        if not healthy:
            if not pause_starts:
                emit("model_endpoint_unhealthy", running=running)
        while healthy and running < int(state["target_concurrency"]):
            candidates = state["tasks"].items()
            candidate = next(
                (
                    (task, entry)
                    for task, entry in candidates
                    if entry["phase"] == "retry_pending"
                ),
                None,
            )
            if candidate is None:
                candidate = next(
                    (
                        (task, entry)
                        for task, entry in state["tasks"].items()
                        if entry["phase"] == "pending"
                    ),
                    None,
                )
            if candidate is None:
                break
            task, entry = candidate
            try:
                start_task(task, entry, state)
                running += 1
            except Exception as error:
                emit("start_request_error", task=task, error=str(error)[:500])
                if "." in task:
                    entry["phase"] = "deferred_runner_update"
                    emit("deferred_runner_update", task=task)
                    continue
                break
        save(state)
        emit(
            "heartbeat",
            completed=completed,
            running=running,
            pending=len(tasks) - completed - exhausted - running,
            concurrency=state["target_concurrency"],
        )
        time.sleep(POLL_SECONDS)


def run() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    pid_path = claim_scheduler()
    try:
        return main()
    finally:
        release_scheduler(pid_path)


if __name__ == "__main__":
    raise SystemExit(run())
