"""Run Coding Kid V01 against 10 SWE-bench Verified instances.

Protocol per instance:
1. Clone repo, checkout base_commit
2. Apply official test_patch
3. Attempt local install (best-effort)
4. Confirm FAIL_TO_PASS tests fail (or record setup failure)
5. Run Coding Kid with the problem_statement only (no step list)
6. Re-run FAIL_TO_PASS tests
7. Also capture git diff as model_patch for optional harness use
"""

from __future__ import annotations

import json
import os
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
INSTANCES_PATH = BASE / "verified_10_instances.json"
WORK_ROOT = BASE / "verified_workspaces"
REPORT_PATH = BASE / "v1_verified_10_report.json"
PATCHES_PATH = BASE / "v1_verified_10_predictions.jsonl"


@dataclass
class InstanceResult:
    instance_id: str
    repo: str
    setup_ok: bool
    pre_fail_ok: bool  # True if fail-to-pass tests correctly fail before agent
    passed_outcome: bool
    duration_s: float
    tool_calls: list[str] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)
    pre_summary: str = ""
    post_summary: str = ""
    answer_preview: str = ""
    model_patch_lines: int = 0
    error: str | None = None
    notes: list[str] = field(default_factory=list)


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def ensure_repo(instance: dict) -> Path:
    instance_id = instance["instance_id"]
    repo = instance["repo"]
    base_commit = instance["base_commit"]
    dest = WORK_ROOT / instance_id
    url = f"https://github.com/{repo}.git"

    if not dest.exists():
        print(f"  cloning {repo}...")
        # Shallow clone then fetch the commit
        r = run(["git", "clone", "--filter=blob:none", "--no-checkout", url, str(dest)], timeout=300)
        if r.returncode != 0:
            raise RuntimeError(f"clone failed: {r.stderr[-500:]}")
    # Fetch and checkout base commit
    r = run(["git", "fetch", "--depth", "1", "origin", base_commit], cwd=dest, timeout=300)
    if r.returncode != 0:
        # fallback deeper fetch
        run(["git", "fetch", "--depth", "50", "origin", base_commit], cwd=dest, timeout=300)
    r = run(["git", "checkout", "-f", base_commit], cwd=dest, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"checkout failed: {r.stderr[-500:]}")
    run(["git", "reset", "--hard", base_commit], cwd=dest)
    run(["git", "clean", "-fd"], cwd=dest)

    # Apply test patch
    patch_file = dest / "_swe_test.patch"
    patch_file.write_text(instance["test_patch"], encoding="utf-8")
    r = run(["git", "apply", "--verbose", str(patch_file)], cwd=dest)
    if r.returncode != 0:
        r = run(["git", "apply", "--verbose", "--reject", str(patch_file)], cwd=dest)
        if r.returncode != 0:
            raise RuntimeError(f"test_patch apply failed: {r.stderr[-500:]}")
    return dest


def best_effort_install(instance: dict, dest: Path) -> list[str]:
    notes: list[str] = []
    repo = instance["repo"]
    # Prefer editable install into project venv
    candidates = [
        [str(VENV_PY), "-m", "pip", "install", "-e", ".[test]", "-q"],
        [str(VENV_PY), "-m", "pip", "install", "-e", ".[testing]", "-q"],
        [str(VENV_PY), "-m", "pip", "install", "-e", ".[tests]", "-q"],
        [str(VENV_PY), "-m", "pip", "install", "-e", ".", "-q"],
    ]
    if "django" in repo:
        candidates.insert(0, [str(VENV_PY), "-m", "pip", "install", "-e", ".", "tblib", "-q"])
    for cmd in candidates:
        r = run(cmd, cwd=dest, timeout=600)
        if r.returncode == 0:
            notes.append(f"install ok via {' '.join(cmd[-3:])}")
            return notes
        notes.append(f"install failed: {' '.join(cmd[-3:])}")
    return notes


def pytest_node_ids(fail_to_pass: list[str] | str) -> list[str]:
    if isinstance(fail_to_pass, str):
        fail_to_pass = json.loads(fail_to_pass)
    return list(fail_to_pass)


def run_fail_tests(dest: Path, node_ids: list[str], timeout: int = 300) -> tuple[bool, str]:
    """Return (all_passed, summary)."""
    # Sympy sometimes uses bare function names
    args = [str(VENV_PY), "-m", "pytest", "-q", "--tb=line", "-p", "no:cacheprovider"]
    # Map bare names if needed
    expanded: list[str] = []
    for nid in node_ids:
        if "::" in nid or "/" in nid or "\\" in nid:
            expanded.append(nid)
        else:
            # search for test file containing this name
            expanded.append("-k")
            expanded.append(nid)
    cmd = args + expanded
    try:
        r = run(cmd, cwd=dest, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "pytest timeout"
    out = (r.stdout + r.stderr).strip()
    summary = " | ".join(out.splitlines()[-6:])
    return r.returncode == 0, summary


def capture_patch(dest: Path) -> str:
    r = run(["git", "diff", "--", ":!_swe_test.patch"], cwd=dest)
    # Exclude the test patch file itself; include tracked source changes
    # Also include untracked new files that aren't the patch
    r2 = run(["git", "ls-files", "--others", "--exclude-standard"], cwd=dest)
    extras = [
        line.strip()
        for line in r2.stdout.splitlines()
        if line.strip() and not line.strip().endswith("_swe_test.patch")
    ]
    patch = r.stdout
    for path in extras:
        r3 = run(["git", "add", "-N", path], cwd=dest)
        r4 = run(["git", "diff", "--", path], cwd=dest)
        patch += r4.stdout
    return patch


def run_agent(dest: Path, problem_statement: str) -> tuple[str, list[str], list[str], str | None]:
    tool_calls: list[str] = []
    tool_errors: list[str] = []
    answer = ""
    error = None
    prompt = (
        problem_statement.strip()
        + "\n\n"
        + "You are in the repository at the current working directory. "
        + "Fix the bug described above. Do not modify the tests. "
        + "Use tools to inspect and change code, then verify your fix."
    )

    def on_tool(name: str, arguments: dict, result: str) -> None:
        tool_calls.append(name)
        preview = json.dumps(arguments, ensure_ascii=False)
        if len(preview) > 120:
            preview = preview[:117] + "..."
        print(f"    [tool] {name} {preview}")
        if result.startswith("ERROR:"):
            tool_errors.append(f"{name}: {result[:180]}")

    original = Path.cwd()
    try:
        os.chdir(dest)
        answer = run_turn([{"role": "user", "content": prompt}], on_tool=on_tool)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-700:]}"
    finally:
        os.chdir(original)
    return answer, tool_calls, tool_errors, error


def process_instance(instance: dict) -> InstanceResult:
    instance_id = instance["instance_id"]
    print(f"\n===== {instance_id} =====")
    start = time.perf_counter()
    notes: list[str] = []
    try:
        dest = ensure_repo(instance)
        notes.extend(best_effort_install(instance, dest))
        node_ids = pytest_node_ids(instance["FAIL_TO_PASS"])
        pre_pass, pre_summary = run_fail_tests(dest, node_ids)
        # We want tests to FAIL before the agent (pre_pass False)
        pre_fail_ok = not pre_pass
        if pre_pass:
            notes.append("WARNING: fail-to-pass tests already passing before agent")
        else:
            notes.append("pre-state: fail-to-pass correctly failing")

        answer, tool_calls, tool_errors, error = run_agent(
            dest, instance["problem_statement"]
        )
        post_pass, post_summary = run_fail_tests(dest, node_ids)
        patch = capture_patch(dest)
        return InstanceResult(
            instance_id=instance_id,
            repo=instance["repo"],
            setup_ok=True,
            pre_fail_ok=pre_fail_ok,
            passed_outcome=post_pass,
            duration_s=time.perf_counter() - start,
            tool_calls=tool_calls,
            tool_errors=tool_errors,
            pre_summary=pre_summary,
            post_summary=post_summary,
            answer_preview=answer[:600],
            model_patch_lines=len(patch.splitlines()),
            error=error,
            notes=notes,
        )
    except Exception as exc:
        return InstanceResult(
            instance_id=instance_id,
            repo=instance["repo"],
            setup_ok=False,
            pre_fail_ok=False,
            passed_outcome=False,
            duration_s=time.perf_counter() - start,
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-800:]}",
            notes=notes,
        )


def main() -> int:
    if not os.getenv("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is not set")
        return 1

    instances = json.loads(INSTANCES_PATH.read_text(encoding="utf-8"))
    WORK_ROOT.mkdir(parents=True, exist_ok=True)

    only = os.getenv("ONLY_INSTANCE")
    if only:
        instances = [i for i in instances if i["instance_id"] == only]

    results: list[InstanceResult] = []
    predictions: list[dict] = []

    for instance in instances:
        result = process_instance(instance)
        results.append(result)
        mark = "PASS" if result.passed_outcome else "FAIL"
        print(
            f"  => [{mark}] setup={result.setup_ok} pre_fail_ok={result.pre_fail_ok} "
            f"{result.duration_s:.1f}s tools={result.tool_calls}"
        )
        if result.error:
            print(f"  error: {result.error[:300]}")
        print(f"  post: {result.post_summary[:200]}")

        # Refresh patch from workspace if present
        dest = WORK_ROOT / instance["instance_id"]
        patch = ""
        if dest.exists():
            patch = capture_patch(dest)
        predictions.append(
            {
                "instance_id": instance["instance_id"],
                "model_name_or_path": "coding-kid-v01",
                "model_patch": patch,
            }
        )

        # Incremental save
        REPORT_PATH.write_text(
            json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        PATCHES_PATH.write_text(
            "\n".join(json.dumps(p, ensure_ascii=False) for p in predictions) + "\n",
            encoding="utf-8",
        )

    passed = sum(1 for r in results if r.passed_outcome)
    setup_ok = sum(1 for r in results if r.setup_ok and r.pre_fail_ok)
    print("\n========== SUMMARY ==========")
    print(f"Valid baselines (setup+pre-fail): {setup_ok}/{len(results)}")
    print(f"Resolved by Coding Kid V01: {passed}/{len(results)}")
    for r in results:
        print(
            f"  {'PASS' if r.passed_outcome else 'FAIL'} {r.instance_id} "
            f"(setup={r.setup_ok}, pre_fail_ok={r.pre_fail_ok}, tools={len(r.tool_calls)})"
        )
    print(f"Report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
