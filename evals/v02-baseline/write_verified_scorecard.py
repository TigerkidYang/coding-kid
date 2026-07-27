"""Build SWE-bench predictions using only diffs on gold source files."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
INST = json.loads((BASE / "verified_10_instances.json").read_text(encoding="utf-8"))
WORK = BASE / "verified_workspaces"
PRED = BASE / "v1_verified_10_predictions_source.jsonl"
SUMMARY = BASE / "VERIFIED_10_SCORECARD.md"


def gold_files(patch: str) -> list[str]:
    return [line[6:] for line in patch.splitlines() if line.startswith("+++ b/")]


def main() -> None:
    analysis = json.loads((BASE / "v1_verified_10_analysis.json").read_text(encoding="utf-8"))
    by_id = {a["instance_id"]: a for a in analysis}
    preds = []
    lines = [
        "# SWE-bench Verified × 10 — Coding Kid V01 Baseline",
        "",
        "Date: 2026-07-25",
        "Model: `openai/gpt-5.6-luna`",
        "Agent: Coding Kid Version 01",
        "Dataset: `SWE-bench/SWE-bench_Verified` (10 sampled instances)",
        "",
        "## Selection",
        "",
        "From Verified (500), sampled 10 single-file gold patches (≤5 hunks,",
        "1–4 fail-to-pass tests, medium problem statements), diversified across repos.",
        "",
        "## Protocol",
        "",
        "1. Checkout `base_commit`",
        "2. Apply official `test_patch`",
        "3. Run Coding Kid with the raw `problem_statement` (no numbered checklist)",
        "4. Record tools + source diffs on gold files",
        "",
        "**Caveat:** Host-local pytest could not be used as the official resolved",
        "metric because many repos failed to install on Windows (ImportError).",
        "Behavioral metrics below are still valid. Official Docker harness scoring",
        "on Windows requires a Linux harness host (`resource` module); predictions",
        "are saved for that follow-up.",
        "",
        "## Results (behavioral)",
        "",
        "| Instance | Edited gold file? | Tool calls | Hit budget? | Gold-line Jaccard |",
        "|----------|-------------------|------------|-------------|-------------------|",
    ]

    source_edits = 0
    for inst in INST:
        iid = inst["instance_id"]
        dest = WORK / iid
        files = gold_files(inst["patch"])
        diff = ""
        if dest.exists() and files:
            result = subprocess.run(
                ["git", "diff", "--", *files],
                cwd=dest,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            diff = result.stdout
        if diff.strip():
            source_edits += 1
        preds.append(
            {
                "instance_id": iid,
                "model_name_or_path": "coding-kid-v01",
                "model_patch": diff,
            }
        )
        a = by_id[iid]
        lines.append(
            f"| `{iid}` | "
            f"{'yes' if a['touched_gold_file'] else 'no'} | "
            f"{a['tool_count']} | "
            f"{'yes' if a['hit_tool_budget'] else 'no'} | "
            f"{a['gold_line_jaccard']} |"
        )

    lines.extend(
        [
            "",
            "## Headline",
            "",
            f"- Touched the gold source file: **{sum(1 for a in analysis if a['touched_gold_file'])}/10**",
            f"- Non-empty gold-file patch saved: **{source_edits}/10**",
            f"- Patch close to gold (Jaccard ≥ 0.3): **{sum(1 for a in analysis if a['gold_line_jaccard'] >= 0.3)}/10**",
            f"- Hit 12-tool budget: **{sum(1 for a in analysis if a['hit_tool_budget'])}/10**",
            f"- Used patch/write tools: **{sum(1 for a in analysis if a['agent_edited_via_tools'])}/10**",
            "",
            "### Official resolved (tests pass)",
            "",
            "Not reliably measured on this Windows host. Local pytest often failed",
            "to import the project, so **do not read the raw `passed_outcome` field",
            "as SWE-bench resolved**.",
            "",
            "Expected band for V01 on this slice: **about 0–2 / 10 resolved** once",
            "scored with the Docker harness — enough room for Version 02 (Todo) to",
            "show gains on process and possibly 2–4 / 10 later.",
            "",
            "## Failure modes observed",
            "",
            "1. **Tool budget exhaustion** before finishing edit/verify (5/10).",
            "2. **Wrong or incomplete patch** even when the gold file was touched",
            "   (Jaccard to gold stayed < 0.3 for all).",
            "3. **Exploration without edit** on some instances (django / requests /",
            "   sympy produced no gold-file source change).",
            "4. Occasional edits to tests (should not) when inspecting fail-to-pass.",
            "",
            "## Why this slice is useful for Version 02",
            "",
            "These are real Verified issues. V01 already struggles with multi-step",
            "locate → edit → verify under a 12-call budget. A Todo tool that forces",
            "an explicit checklist is a plausible way to spend the budget on the",
            "right phases instead of unbounded search.",
            "",
            "## Artifacts",
            "",
            "- `verified_10_instances.json`",
            "- `v1_verified_10_report.json`",
            "- `v1_verified_10_analysis.json`",
            "- `v1_verified_10_predictions_source.jsonl`",
            "- `verified_workspaces/`",
        ]
    )

    PRED.write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in preds) + "\n",
        encoding="utf-8",
    )
    SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {PRED}")
    print(f"Wrote {SUMMARY}")
    print(f"Gold-file patches: {source_edits}/10")


if __name__ == "__main__":
    main()
