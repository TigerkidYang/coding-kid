"""Collect patches from verified workspaces and summarize V01 behavior.

Also attempts an honest local re-check: did the agent edit the gold file?
Did the patch resemble the gold patch?
Official Docker harness scoring is preferred when available.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
INSTANCES = json.loads((BASE / "verified_10_instances.json").read_text(encoding="utf-8"))
REPORT = json.loads((BASE / "v1_verified_10_report.json").read_text(encoding="utf-8"))
WORK = BASE / "verified_workspaces"
OUT = BASE / "v1_verified_10_analysis.json"
PRED = BASE / "v1_verified_10_predictions.jsonl"


def gold_files(patch: str) -> list[str]:
    return [line[6:] for line in patch.splitlines() if line.startswith("+++ b/")]


def capture_source_diff(dest: Path) -> str:
    r = subprocess.run(
        ["git", "diff", "--", ":!_swe_test.patch", ":!*_swe_test.patch"],
        cwd=dest,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return r.stdout


def changed_files(diff: str) -> list[str]:
    files = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[6:])
    return files


def main() -> None:
    by_id = {r["instance_id"]: r for r in REPORT}
    predictions = []
    analysis = []

    for inst in INSTANCES:
        iid = inst["instance_id"]
        dest = WORK / iid
        gold = gold_files(inst["patch"])
        agent_diff = capture_source_diff(dest) if dest.exists() else ""
        changed = changed_files(agent_diff)
        report = by_id.get(iid, {})
        tools = report.get("tool_calls", [])
        edited = bool(set(tools) & {"patch", "write", "delete"})
        touched_gold = any(g.replace("\\", "/") in {c.replace("\\", "/") for c in changed} for g in gold)
        # crude similarity: shared removed/added lines
        gold_lines = set(
            line[1:].strip()
            for line in inst["patch"].splitlines()
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        )
        agent_lines = set(
            line[1:].strip()
            for line in agent_diff.splitlines()
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        )
        overlap = len(gold_lines & agent_lines)
        union = len(gold_lines | agent_lines) or 1

        row = {
            "instance_id": iid,
            "repo": inst["repo"],
            "gold_files": gold,
            "agent_changed_files": changed,
            "agent_edited_via_tools": edited,
            "touched_gold_file": touched_gold,
            "tool_calls": tools,
            "tool_count": len(tools),
            "hit_tool_budget": len(tools) >= 12,
            "patch_line_count": len(agent_diff.splitlines()),
            "gold_line_overlap": overlap,
            "gold_line_jaccard": round(overlap / union, 3),
            "local_pytest_passed": report.get("passed_outcome"),
            "answer_preview": (report.get("answer_preview") or "")[:300],
            "install_notes": report.get("notes", []),
        }
        analysis.append(row)
        predictions.append(
            {
                "instance_id": iid,
                "model_name_or_path": "coding-kid-v01",
                "model_patch": agent_diff,
            }
        )

    OUT.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    PRED.write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in predictions) + "\n",
        encoding="utf-8",
    )

    print("SWE-bench Verified x10 — Coding Kid V01 analysis")
    print("=" * 60)
    edited_n = sum(1 for a in analysis if a["agent_edited_via_tools"])
    touched_n = sum(1 for a in analysis if a["touched_gold_file"])
    budget_n = sum(1 for a in analysis if a["hit_tool_budget"])
    nonempty_patch = sum(1 for a in analysis if a["patch_line_count"] > 0)
    print(f"Edited with patch/write: {edited_n}/10")
    print(f"Non-empty source diff:   {nonempty_patch}/10")
    print(f"Touched gold file:       {touched_n}/10")
    print(f"Hit 12-tool budget:      {budget_n}/10")
    print()
    for a in analysis:
        flags = []
        if a["touched_gold_file"]:
            flags.append("gold-file")
        if a["hit_tool_budget"]:
            flags.append("budget")
        if a["patch_line_count"] == 0:
            flags.append("no-diff")
        print(
            f"- {a['instance_id']}: tools={a['tool_count']} "
            f"overlap={a['gold_line_jaccard']} [{', '.join(flags) or 'edited'}]"
        )
    print(f"\nWrote {OUT}")
    print(f"Wrote {PRED}")
    print(
        "\nNOTE: Local pytest PASS/FAIL in the raw report is NOT trustworthy when "
        "installs failed (ImportError counted as failure). Use Docker SWE-bench "
        "harness for official resolved counts."
    )


if __name__ == "__main__":
    main()
