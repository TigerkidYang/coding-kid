import json
import subprocess
from pathlib import Path

BASE = Path("evals/v02-baseline")
INST = json.loads((BASE / "verified_10_instances.json").read_text(encoding="utf-8"))
REP = {
    r["instance_id"]: r
    for r in json.loads((BASE / "v1_verified_10_report.json").read_text(encoding="utf-8"))
}
WORK = BASE / "verified_workspaces"
analysis = []
preds = []

for inst in INST:
    iid = inst["instance_id"]
    dest = WORK / iid
    tools = REP.get(iid, {}).get("tool_calls", [])
    gold = [line[6:] for line in inst["patch"].splitlines() if line.startswith("+++ b/")]
    diff = ""
    if dest.exists():
        result = subprocess.run(
            ["git", "diff"],
            cwd=dest,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        diff = result.stdout
        # Drop the helper patch file from the textual patch if present as untracked only.
    changed = [line[6:] for line in diff.splitlines() if line.startswith("+++ b/")]
    touched = any(
        g.replace("\\", "/") in {c.replace("\\", "/") for c in changed} for g in gold
    )
    gold_lines = {
        line[1:].strip()
        for line in inst["patch"].splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    }
    agent_lines = {
        line[1:].strip()
        for line in diff.splitlines()
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
        "touched_gold_file": touched,
        "tool_calls": tools,
        "tool_count": len(tools),
        "hit_tool_budget": len(tools) >= 12,
        "patch_line_count": len(diff.splitlines()),
        "gold_line_overlap": overlap,
        "gold_line_jaccard": round(overlap / union, 3),
        "answer_preview": (REP.get(iid, {}).get("answer_preview") or "")[:300],
    }
    analysis.append(row)
    preds.append(
        {
            "instance_id": iid,
            "model_name_or_path": "coding-kid-v01",
            "model_patch": diff,
        }
    )
    print(
        f"{iid}: edit_tools={row['agent_edited_via_tools']} lines={row['patch_line_count']} "
        f"gold_touch={touched} jaccard={row['gold_line_jaccard']} files={changed}"
    )

print("---")
print("edited_tools", sum(1 for a in analysis if a["agent_edited_via_tools"]))
print("nonempty_diff", sum(1 for a in analysis if a["patch_line_count"] > 0))
print("gold_touch", sum(1 for a in analysis if a["touched_gold_file"]))
print("jaccard>=0.3", sum(1 for a in analysis if a["gold_line_jaccard"] >= 0.3))
print("budget", sum(1 for a in analysis if a["hit_tool_budget"]))

(BASE / "v1_verified_10_analysis.json").write_text(
    json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8"
)
(BASE / "v1_verified_10_predictions.jsonl").write_text(
    "\n".join(json.dumps(p, ensure_ascii=False) for p in preds) + "\n",
    encoding="utf-8",
)
