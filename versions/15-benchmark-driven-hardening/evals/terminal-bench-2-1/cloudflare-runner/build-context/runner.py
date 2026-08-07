from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()
workspace = Path("/workspace")
state_path = workspace / "state.json"
log_path = workspace / "harbor.log"
docker_ready_path = workspace / "docker.ready"
docker_failed_path = workspace / "docker.failed"
lock = threading.Lock()
process: subprocess.Popen[str] | None = None


class StartRequest(BaseModel):
    task: str


def run_checked(command: list[str], timeout: int) -> dict[str, object]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "command": command,
        "return_code": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def read_state() -> dict[str, object]:
    if not state_path.exists():
        return {"phase": "idle"}
    return json.loads(state_path.read_text(encoding="utf-8"))


def write_state(value: dict[str, object]) -> None:
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(state_path)


def resource_snapshot() -> dict[str, object]:
    memory_current = Path("/sys/fs/cgroup/memory.current")
    memory_max = Path("/sys/fs/cgroup/memory.max")
    usage = shutil.disk_usage(workspace)
    return {
        "docker_ready": docker_ready_path.exists(),
        "docker_failed": docker_failed_path.exists(),
        "memory_current": int(memory_current.read_text().strip()) if memory_current.exists() else None,
        "memory_max": memory_max.read_text().strip() if memory_max.exists() else None,
        "disk_used": usage.used,
        "disk_free": usage.free,
    }


def find_result(job_dir: Path) -> dict[str, object] | None:
    candidates = sorted(job_dir.rglob("result.json"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        return None
    return json.loads(candidates[-1].read_text(encoding="utf-8"))


def find_trial_diagnostics(job_dir: Path) -> list[dict[str, object]]:
    diagnostics: list[dict[str, object]] = []
    for result_path in sorted(job_dir.rglob("result.json")):
        if result_path.parent == job_dir:
            continue
        value = json.loads(result_path.read_text(encoding="utf-8"))
        diagnostics.append({
            "path": str(result_path.relative_to(job_dir)),
            "trial_name": value.get("trial_name"),
            "exception_info": value.get("exception_info"),
            "agent_info": value.get("agent_info"),
            "verifier_result": value.get("verifier_result"),
        })
    return diagnostics


def execute(task: str, trial_id: str, preflight: bool = False) -> None:
    global process
    started = time.time()
    job_dir = workspace / "jobs" / trial_id
    command = [
        "harbor", "run",
        "--path", f"/opt/dataset/{task}",
        "--n-attempts", "1",
        "--n-concurrent", "1",
        "--no-force-build",
        "--yes",
        "--jobs-dir", str(workspace / "jobs"),
        "--job-name", trial_id,
        "--extra-docker-compose", "/opt/host-network.yaml",
        "--cpus", "ignore",
        "--memory", "ignore",
    ]
    if preflight:
        command.extend([
            "--agent-import-path",
            "coding_kid_harbor:CodingKidPreflightAgent",
        ])
    else:
        command.extend([
            "--agent-import-path", "coding_kid_harbor:CodingKidAgent",
            "--model", "gpt-5.6-luna",
        ])
    run_kind = "preflight" if preflight else "benchmark"
    write_state({
        "phase": "running",
        "kind": run_kind,
        "task": task,
        "trial_id": trial_id,
        "started_at": started,
    })
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, text=True)
        return_code = process.wait()
    result = find_result(job_dir)
    errored_trials = None
    if result is not None:
        stats = result.get("stats")
        if isinstance(stats, dict):
            errored_trials = stats.get("n_errored_trials")
    phase = (
        "completed"
        if return_code == 0 and result is not None and errored_trials == 0
        else "infrastructure_error"
    )
    write_state({
        "phase": phase,
        "kind": run_kind,
        "task": task,
        "trial_id": trial_id,
        "started_at": started,
        "finished_at": time.time(),
        "return_code": return_code,
        "result": result,
        "trial_diagnostics": find_trial_diagnostics(job_dir),
    })


@app.get("/ping")
def ping() -> dict[str, bool]:
    return {"ok": True}


@app.post("/docker-smoke")
def docker_smoke() -> dict[str, object]:
    with lock:
        if process is not None and process.poll() is None:
            raise HTTPException(status_code=409, detail="Harbor is running")
        version = run_checked(["docker", "version"], timeout=30)
        if version["return_code"] != 0:
            raise HTTPException(status_code=500, detail={"docker_version": version})
        nested = run_checked(
            [
                "docker", "run", "--rm", "--network=host",
                "alpine:3.21", "printf", "nested-ok",
            ],
            timeout=300,
        )
        if nested["return_code"] != 0 or nested["stdout"] != "nested-ok":
            raise HTTPException(
                status_code=500,
                detail={"docker_version": version, "nested_container": nested},
            )
        return {"ok": True, "docker_version": version, "nested_container": nested}


@app.post("/start")
def start(request: StartRequest) -> dict[str, object]:
    global process
    if not docker_ready_path.exists():
        raise HTTPException(status_code=503, detail="Docker daemon is not ready")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,62}", request.task):
        raise HTTPException(status_code=400, detail="invalid task")
    task_dir = Path("/opt/dataset") / request.task
    if not task_dir.is_dir():
        raise HTTPException(status_code=404, detail="unknown task")
    trial_id = os.environ.get("BENCHMARK_TRIAL_ID", "trial")[-32:].lower()
    with lock:
        state = read_state()
        if state.get("phase") == "running" and process is not None and process.poll() is None:
            return state
        if state.get("phase") == "completed":
            return state
        thread = threading.Thread(target=execute, args=(request.task, trial_id), daemon=True)
        thread.start()
    return read_state()


@app.post("/preflight")
def preflight(request: StartRequest) -> dict[str, object]:
    global process
    if not docker_ready_path.exists():
        raise HTTPException(status_code=503, detail="Docker daemon is not ready")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,62}", request.task):
        raise HTTPException(status_code=400, detail="invalid task")
    if not (Path("/opt/dataset") / request.task).is_dir():
        raise HTTPException(status_code=404, detail="unknown task")
    trial_id = os.environ.get("BENCHMARK_TRIAL_ID", "preflight")[-32:].lower()
    with lock:
        state = read_state()
        if state.get("phase") == "running" and process is not None and process.poll() is None:
            return state
        thread = threading.Thread(
            target=execute,
            args=(request.task, trial_id, True),
            daemon=True,
        )
        thread.start()
    return read_state()


@app.get("/status")
def status() -> dict[str, object]:
    state = read_state()
    state["resources"] = resource_snapshot()
    state["harbor_log_tail"] = ""
    if log_path.exists():
        state["harbor_log_tail"] = log_path.read_text(encoding="utf-8", errors="replace")[-12000:]
    dockerd_log = workspace / "dockerd.log"
    state["dockerd_log_tail"] = ""
    if dockerd_log.exists():
        state["dockerd_log_tail"] = dockerd_log.read_text(encoding="utf-8", errors="replace")[-4000:]
    agent_logs = sorted(
        (workspace / "jobs").rglob("coding-kid.txt"),
        key=lambda path: path.stat().st_mtime,
    )
    state["agent_log_tail"] = ""
    if agent_logs:
        state["agent_log_tail"] = agent_logs[-1].read_text(
            encoding="utf-8", errors="replace"
        )[-12000:]
    return state
