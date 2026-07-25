"""Investigate why V02 scored 0/10 vs V01 5/10 on the same Verified slice."""

from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
V1_RESOLVED = {
    "astropy__astropy-12907",
    "matplotlib__matplotlib-13989",
    "pytest-dev__pytest-5809",
    "scikit-learn__scikit-learn-15100",
    "sphinx-doc__sphinx-8269",
}


def load_preds(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[row["instance_id"]] = row.get("model_patch") or ""
    return out


def summarize_patch(patch: str) -> str:
    files = [ln[6:] for ln in patch.splitlines() if ln.startswith("+++ b/")]
    added = sum(1 for ln in patch.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in patch.splitlines() if ln.startswith("-") and not ln.startswith("---"))
    return f"files={files} +{added}/-{removed} chars={len(patch)}"


def harness_fail_reason(instance_id: str, version: str) -> str:
    root = BASE / "logs" / "run_evaluation"
    if version == "v01":
        report = (
            root
            / "coding_kid_v01_verified10"
            / "coding-kid-v01"
            / instance_id
            / "report.json"
        )
        test_out = report.parent / "test_output.txt"
    else:
        report = (
            root
            / "coding_kid_v02_verified10"
            / "coding-kid-v02"
            / instance_id
            / "report.json"
        )
        test_out = report.parent / "test_output.txt"
    if not report.exists():
        return "no report.json"
    data = json.loads(report.read_text(encoding="utf-8"))
    entry = data.get(instance_id, data)
    resolved = entry.get("resolved")
    tests = entry.get("tests_status", {})
    ftp = tests.get("FAIL_TO_PASS", {})
    ptp = tests.get("PASS_TO_PASS", {})
    bits = [
        f"resolved={resolved}",
        f"ftp_success={ftp.get('success')}",
        f"ftp_failure={ftp.get('failure')}",
        f"ptp_fail_count={len(ptp.get('failure') or [])}",
    ]
    if test_out.exists():
        text = test_out.read_text(encoding="utf-8", errors="replace")
        # Keep last failure-looking lines.
        lines = [ln for ln in text.splitlines() if ln.strip()]
        tail = " | ".join(lines[-8:])
        bits.append(f"test_tail={tail[:500]}")
    return " ; ".join(bits)


def main() -> None:
    v1_analysis = {
        r["instance_id"]: r
        for r in json.loads((BASE / "v1_verified_10_analysis.json").read_text(encoding="utf-8"))
    }
    v2_analysis = {
        r["instance_id"]: r
        for r in json.loads((BASE / "v2_verified_10_analysis.json").read_text(encoding="utf-8"))
    }
    v1_preds = load_preds(BASE / "v1_verified_10_predictions_source.jsonl")
    v2_preds = load_preds(BASE / "v2_verified_10_predictions_source.jsonl")

    print("=== Focus: IDs V01 resolved, V02 unresolved ===\n")
    for iid in sorted(V1_RESOLVED):
        a = v1_analysis[iid]
        b = v2_analysis[iid]
        print(f"## {iid}")
        print(f"V1 tools={a['tool_count']} gold={a['touched_gold_file']} j={a['gold_line_jaccard']}")
        print(f"V1 seq={a['tool_calls']}")
        print(f"V1 patch: {summarize_patch(v1_preds.get(iid, ''))}")
        print(f"V1 harness: {harness_fail_reason(iid, 'v01')}")
        print(f"V2 tools={b['tool_count']} gold={b['touched_gold_file']} j={b['gold_line_jaccard']} todo={b.get('todo_calls')}")
        print(f"V2 seq={b['tool_calls']}")
        print(f"V2 patch: {summarize_patch(v2_preds.get(iid, ''))}")
        print(f"V2 harness: {harness_fail_reason(iid, 'v02')}")
        same = (v1_preds.get(iid, "").strip() == v2_preds.get(iid, "").strip())
        print(f"patches_identical={same}")
        print()


if __name__ == "__main__":
    main()
