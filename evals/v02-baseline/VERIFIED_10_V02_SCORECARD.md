# SWE-bench Verified × 10 — Coding Kid V02 vs V01

Date: 2026-07-26
Model: `openai/gpt-5.6-luna`
Agent: Coding Kid Version 02 (`todo` tool; todo excluded from tool budget)
Dataset: same 10 instances as the Version 01 baseline

## Official harness

| Version | Resolved | Unresolved | Empty patch | Errors |
|---------|----------|------------|-------------|--------|
| V01 | **5 / 10** | 2 / 10 | 3 / 10 | 0 / 10 |
| V02 | **0 / 10** | 10 / 10 | 0 / 10 | 0 / 10 |

Harness reused **10 local** `sweb.eval` images (`Found 10 existing instance images`).
No multi-GB re-download. Images kept (`--cache_level instance`).

Report: `coding-kid-v02.coding_kid_v02_verified10.json`

### V01 resolved IDs (reference)

- `astropy__astropy-12907`
- `matplotlib__matplotlib-13989`
- `pytest-dev__pytest-5809`
- `scikit-learn__scikit-learn-15100`
- `sphinx-doc__sphinx-8269`

### V02 result

All 10 completed with non-empty patches; **none** passed fail-to-pass tests.

## Behavioral comparison

| Metric | V01 | V02 (budget-fix rerun) |
|--------|-----|-------------------------|
| Used `todo` | 0 / 10 | **10 / 10** |
| Touched gold source file | **7 / 10** | 6 / 10 |
| Hit 12 file/shell tool budget | 5 / 10 | 10 / 10* |
| Non-empty collected source patch | 10 / 10 | 10 / 10 |
| Patch close to gold (Jaccard ≥ 0.3) | 0 / 10 | 0 / 10 |

\* Analysis counts every tool name in the log; with todo excluded from the
runtime budget the agent still often spends the full 12 file/shell calls.

## Interpretation

- Mirror + pre-pull path works: full harness ran without image-pull failures.
- Todo is reliably used (process goal met).
- Official outcome **regressed** vs V01 on this slice (5 → 0). Todo alone did
  not improve resolved count; planning overhead may still crowd out editing
  quality within the same overall turn limits.
- Next work should investigate failed V01-resolved IDs under V02 (wrong or
  incomplete patches) before treating this slice as a Todo success metric.

## Artifacts

- `v2_verified_10_report.json`
- `v2_verified_10_analysis.json`
- `v2_verified_10_predictions_source.jsonl`
- `v2_verified_10_run_budgetfix.log`
- `coding-kid-v02.coding_kid_v02_verified10.json`
- `harness_reports/v02_verified10.log`
