# SWE-bench Verified × 10 — Coding Kid V01 Baseline

Date: 2026-07-25
Model: `openai/gpt-5.6-luna`
Agent: Coding Kid Version 01
Dataset: `SWE-bench/SWE-bench_Verified` (10 sampled instances)

## Official harness result

```text
Resolved:     5 / 10
Unresolved:   2 / 10
Empty patch:  3 / 10
Errors:       0 / 10
```

Harness: Docker SWE-bench `run_evaluation`  
Run id: `coding_kid_v01_verified10`  
Report: `coding-kid-v01.coding_kid_v01_verified10.json`

Gold harness smoke test (`pytest-dev__pytest-5809`): **1 / 1 resolved** (setup OK).

### Per instance

| Instance | Official result |
|----------|-----------------|
| `astropy__astropy-12907` | **resolved** |
| `matplotlib__matplotlib-13989` | **resolved** |
| `pytest-dev__pytest-5809` | **resolved** |
| `scikit-learn__scikit-learn-15100` | **resolved** |
| `sphinx-doc__sphinx-8269` | **resolved** |
| `pydata__xarray-2905` | unresolved |
| `pylint-dev__pylint-4970` | unresolved |
| `django__django-15278` | empty patch |
| `psf__requests-5414` | empty patch |
| `sympy__sympy-20590` | empty patch |

## Selection

From Verified (500), sampled 10 single-file gold patches (≤5 hunks,
1–4 fail-to-pass tests, medium problem statements), diversified across repos.

## Protocol

1. Checkout `base_commit`
2. Apply official `test_patch`
3. Run Coding Kid with the raw `problem_statement` (no numbered checklist)
4. Collect gold-file source diffs as `model_patch`
5. Score with official Docker harness

## Behavioral notes (during agent runs)

| Metric | Count |
|--------|-------|
| Touched gold source file | 7 / 10 |
| Hit 12-tool budget | 5 / 10 |
| Patch close to gold text (Jaccard ≥ 0.3) | 0 / 10 |

Resolved patches were often **not textually close to gold**, but still passed
fail-to-pass tests (alternate valid fixes are possible).

## Implications for Version 02

- This slice is **not too hard**: V01 already gets **5 / 10**.
- There is still room: **5 failures** (2 wrong patches + 3 no patch).
- Todo is most likely to help the **empty-patch / budget-exhaustion** cases
  (`django`, `requests`, `sympy`) and incomplete edits (`xarray`, `pylint`).
- If V02 only improves process on already-resolved tasks, that is weak evidence;
  look for gains on the 5 failing IDs.

## Artifacts

- `verified_10_instances.json`
- `v1_verified_10_report.json`
- `v1_verified_10_analysis.json`
- `v1_verified_10_predictions_source.jsonl`
- `coding-kid-v01.coding_kid_v01_verified10.json`
- `harness_reports/v01_verified10.log`
- `verified_workspaces/`
