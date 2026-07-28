"""Rank SWE-bench Verified tasks for V02 task-decomposition calibration.

The ranking uses only benchmark metadata, hidden gold-patch structure, and
public aggregate outcomes from established agents. It never uses Coding Kid V02
results. The output is a candidate list for human inspection, not a final set.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from datasets import load_dataset

BASE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = BASE / "candidate_ranking.json"
DATASET_NAME = "SWE-bench/SWE-bench_Verified"

# A deliberately mixed group of public scaffolds and model strengths. We use
# only their official resolved lists to avoid treating one leaderboard entry as
# a ground-truth difficulty label.
PUBLIC_RUNS = [
    "20241022_tools_claude-3-5-haiku",
    "20241022_tools_claude-3-5-sonnet-updated",
    "20241028_agentless-1.5_gpt4o",
    "20241029_OpenHands-CodeAct-2.1-sonnet-20241022",
    "20241108_autocoderover-v2.0-claude-3-5-sonnet-20241022",
    "20250225_sweagent_claude-3-7-sonnet",
    "20250511_sweagent_lm_32b",
    "20250520_openhands_devstral_small",
]
RESULTS_URL = (
    "https://raw.githubusercontent.com/SWE-bench/experiments/main/"
    "evaluation/verified/{run}/results/results.json"
)

PREVIOUS_SLICE = {
    "astropy__astropy-12907",
    "django__django-15278",
    "matplotlib__matplotlib-13989",
    "psf__requests-5414",
    "pydata__xarray-2905",
    "pylint-dev__pylint-4970",
    "pytest-dev__pytest-5809",
    "scikit-learn__scikit-learn-15100",
    "sphinx-doc__sphinx-8269",
    "sympy__sympy-20590",
}

NON_SOURCE_PARTS = (
    "/test",
    "tests/",
    "test_",
    "docs/",
    "doc/",
    "changelog",
    "news/",
)
MULTI_REQUIREMENT_MARKERS = (
    "\nand ",
    "\nalso ",
    "\n* ",
    "\n- ",
    " should ",
    " must ",
    " additionally ",
    " instead ",
)


@dataclass
class Candidate:
    instance_id: str
    repo: str
    title: str
    source_files: list[str]
    source_file_count: int
    patch_changed_lines: int
    fail_to_pass_count: int
    problem_chars: int
    public_resolved: int
    public_runs: int
    decomposition_score: int


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "coding-kid-v02-evaluation"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def public_resolution_counts() -> Counter[str]:
    counts: Counter[str] = Counter()
    for run in PUBLIC_RUNS:
        result = fetch_json(RESULTS_URL.format(run=run))
        counts.update(result.get("resolved", []))
    return counts


def changed_source_files(patch: str) -> list[str]:
    paths = re.findall(r"^diff --git a/(.+?) b/(.+?)$", patch, re.MULTILINE)
    return sorted(
        {
            target
            for _, target in paths
            if not any(part in target.lower() for part in NON_SOURCE_PARTS)
        }
    )


def changed_line_count(patch: str) -> int:
    return sum(
        1
        for line in patch.splitlines()
        if (line.startswith("+") or line.startswith("-"))
        and not line.startswith("+++")
        and not line.startswith("---")
    )


def parse_list(value: list[str] | str) -> list[str]:
    return json.loads(value) if isinstance(value, str) else value


def task_score(
    row: dict[str, Any],
    source_files: list[str],
    patch_lines: int,
    fail_tests: list[str],
    public_resolved: int,
) -> int:
    score = 0
    source_count = len(source_files)
    if 2 <= source_count <= 4:
        score += 4
    if source_count >= 3:
        score += 1
    if 10 <= patch_lines <= 90:
        score += 2
    if 1 <= len(fail_tests) <= 8:
        score += 1
    if 2 <= public_resolved <= len(PUBLIC_RUNS) - 2:
        score += 3
    problem = row["problem_statement"].lower()
    marker_count = sum(problem.count(marker) for marker in MULTI_REQUIREMENT_MARKERS)
    score += min(marker_count, 3)
    if 500 <= len(problem) <= 3500:
        score += 1
    return score


def build_ranking() -> list[Candidate]:
    resolved_counts = public_resolution_counts()
    dataset = load_dataset(DATASET_NAME, split="test")
    candidates: list[Candidate] = []
    for raw_row in dataset:
        row = dict(raw_row)
        if row["instance_id"] in PREVIOUS_SLICE:
            continue
        source_files = changed_source_files(row["patch"])
        patch_lines = changed_line_count(row["patch"])
        fail_tests = parse_list(row["FAIL_TO_PASS"])
        if not (
            2 <= len(source_files) <= 4
            and 5 <= patch_lines <= 100
            and len(fail_tests) <= 12
            and len(row["problem_statement"]) <= 5000
        ):
            continue
        public_resolved = resolved_counts[row["instance_id"]]
        title = row["problem_statement"].strip().splitlines()[0][:160]
        candidates.append(
            Candidate(
                instance_id=row["instance_id"],
                repo=row["repo"],
                title=title,
                source_files=source_files,
                source_file_count=len(source_files),
                patch_changed_lines=patch_lines,
                fail_to_pass_count=len(fail_tests),
                problem_chars=len(row["problem_statement"]),
                public_resolved=public_resolved,
                public_runs=len(PUBLIC_RUNS),
                decomposition_score=task_score(
                    row,
                    source_files,
                    patch_lines,
                    fail_tests,
                    public_resolved,
                ),
            )
        )
    return sorted(
        candidates,
        key=lambda item: (
            -item.decomposition_score,
            abs(item.public_resolved - len(PUBLIC_RUNS) / 2),
            item.patch_changed_lines,
            item.instance_id,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()

    ranking = build_ranking()
    payload = {
        "dataset": DATASET_NAME,
        "public_runs": PUBLIC_RUNS,
        "selection_note": (
            "Calibration candidates only. Do not treat this ranking as the "
            "frozen final evaluation set."
        ),
        "candidates": [asdict(item) for item in ranking],
    }
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    for item in ranking[: args.limit]:
        print(
            f"{item.decomposition_score:2d} "
            f"public={item.public_resolved}/{item.public_runs} "
            f"files={item.source_file_count} lines={item.patch_changed_lines:3d} "
            f"tests={item.fail_to_pass_count:2d} {item.instance_id} "
            f"- {item.title}"
        )
    print(f"Wrote {len(ranking)} candidates to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
