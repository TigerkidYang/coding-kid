"""Re-collect clean agent patches (commit test_patch first) and compare to gold."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
INSTANCES = json.loads((BASE / "verified_10_instances.json").read_text(encoding="utf-8"))
REPORT = {r["instance_id"]: r for r in json.loads((BASE / "v1_verified_10_report.json").read_text(encoding="utf-8"))}
WORK = BASE / "verified_workspaces"
OUT = BASE / "v1_verified_10_analysis.json"
PRED = BASE / "v1_verified_10_predictions.jsonl"


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def gold_files(patch: str) -> list[str]:
    return [line[6:] for line in patch.splitlines() if line.startswith("+++ b/")]


def clean_agent_diff(dest: Path, base_commit: str, test_patch: str) -> str:
    """Reset to base, apply+commit test_patch, restore agent tree, diff."""
    # Save current tree
    run(["git", "add", "-A"], cwd=dest)
    run(["git", "stash", "push", "-u", "-m", "agent-state"], cwd=dest)

    run(["git", "checkout", "-f", base_commit], cwd=dest)
    run(["git", "clean", "-fd"], cwd=dest)
    patch_path = dest / "_swe_test.patch"
    patch_path.write_text(test_patch, encoding="utf-8")
    r = run(["git", "apply", str(patch_path)], cwd=dest)
    if r.returncode != 0:
        run(["git", "stash", "pop"], cwd=dest)
        return ""
    # Never commit the helper patch file — its later deletion pollutes model_patch
    # and makes the SWE-bench harness reverse-apply the real source fix.
    patch_path.unlink(missing_ok=True)
    run(["git", "add", "-A"], cwd=dest)
    run(
        ["git", "commit", "--no-gpg-sign", "-m", "swe test_patch"],
        cwd=dest,
    )
    # Restore agent changes on top
    r = run(["git", "stash", "pop"], cwd=dest)
    # Remove helper patch file from diff noise
    if patch_path.exists():
        patch_path.unlink()
    # Diff against test_patch commit
    r = run(["git", "diff"], cwd=dest)
    return strip_helper_patch_hunks(r.stdout)


def strip_helper_patch_hunks(diff: str) -> str:
    """Drop any leftover hunks that touch the local helper patch file."""
    lines = diff.splitlines(keepends=True)
    kept: list[str] = []
    skipping = False
    for line in lines:
        if line.startswith("diff --git ") and "_swe_test.patch" in line:
            skipping = True
            continue
        if skipping:
            if line.startswith("diff --git "):
                skipping = False
            else:
                continue
        if not skipping:
            kept.append(line)
    return "".join(kept)


def changed_files(diff: str) -> list[str]:
    return [line[6:] for line in diff.splitlines() if line.startswith("+++ b/")]


def main() -> None:
    analysis = []
    predictions = []

    for inst in INSTANCES:
        iid = inst["instance_id"]
        dest = WORK / iid
        report = REPORT.get(iid, {})
        tools = report.get("tool_calls", [])
        gold = gold_files(inst["patch"])
        agent_diff = ""
        if dest.exists():
            try:
                agent_diff = clean_agent_diff(
                    dest, inst["base_commit"], inst["test_patch"]
                )
            except Exception as exc:
                agent_diff = f""
                print(f"{iid}: clean_agent_diff failed: {exc}")

        changed = changed_files(agent_diff)
        touched_gold = any(
            g.replace("\\", "/") in {c.replace("\\", "/") for c in changed} for g in gold
        )
        gold_lines = {
            line[1:].strip()
            for line in inst["patch"].splitlines()
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        }
        agent_lines = {
            line[1:].strip()
            for line in agent_diff.splitlines()
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        }
        overlap = len(gold_lines & agent_lines)
        union = len(gold_lines | agent_lines) or 1

        row = {
            "instance_id": iid,
            "repo": inst["repo"],
            "gold_files": gold,
            "agent_changed_files": changed,
            "agent_edited_via_tools": bool(set(tools) & {"patch", "write", "delete"}),
            "touched_gold_file": touched_gold,
            "tool_calls": tools,
            "tool_count": len(tools),
            "hit_tool_budget": len(tools) >= 12,
            "patch_line_count": len(agent_diff.splitlines()),
            "gold_line_overlap": overlap,
            "gold_line_jaccard": round(overlap / union, 3),
            "answer_preview": (report.get("answer_preview") or "")[:300],
        }
        analysis.append(row)
        predictions.append(
            {
                "instance_id": iid,
                "model_name_or_path": "coding-kid-v01",
                "model_patch": agent_diff,
            }
        )
        status = "EDIT" if row["patch_line_count"] else "NO_DIFF"
        print(
            f"[{status}] {iid}: tools={row['tool_count']} "
            f"gold_touch={row['touched_gold_file']} jaccard={row['gold_line_jaccard']} "
            f"files={changed}"
        )

    OUT.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    PRED.write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in predictions) + "\n",
        encoding="utf-8",
    )

    edited = sum(1 for a in analysis if a["patch_line_count"] > 0)
    gold_touch = sum(1 for a in analysis if a["touched_gold_file"])
    close = sum(1 for a in analysis if a["gold_line_jaccard"] >= 0.3)
    budget = sum(1 for a in analysis if a["hit_tool_budget"])
    print("\n==== SUMMARY ====")
    print(f"Produced a source patch: {edited}/10")
    print(f"Touched gold file:       {gold_touch}/10")
    print(f"Patch resembles gold:    {close}/10 (jaccard>=0.3)")
    print(f"Hit tool budget:         {budget}/10")
    print(
        "Official resolved count still requires Docker SWE-bench harness "
        "(Windows host cannot import swebench.harness.resource)."
    )


if __name__ == "__main__":
    main()
