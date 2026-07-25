# SWE-bench Verified × 10 — Coding Kid V02 vs V01

Date: 2026-07-26
Model: `openai/gpt-5.6-luna`
Agent: Coding Kid Version 02 (`todo` tool; todo excluded from tool budget)
Dataset: same 10 instances as the Version 01 baseline

## Official harness

| Version | Resolved | Unresolved | Empty patch | Errors |
|---------|----------|------------|-------------|--------|
| V01 | **5 / 10** | 2 / 10 | 3 / 10 | 0 / 10 |
| V02 (contaminated preds) | 0 / 10 | 10 / 10 | 0 / 10 | 0 / 10 |
| V02 (cleaned preds) | **5 / 10** | 1 / 10 | 4 / 10 | 0 / 10 |

The contaminated run was invalid: every prediction deleted helper file
`_swe_test.patch`, which made the harness reverse-apply source fixes. See
`INVESTIGATION_V02_REGRESSION.md`.

Cleaned report: `coding-kid-v02.coding_kid_v02_verified10_clean.json`  
Harness reused 10 local images; no re-download.

### Resolved IDs

V01:

- `astropy__astropy-12907`
- `matplotlib__matplotlib-13989`
- `pytest-dev__pytest-5809`
- `scikit-learn__scikit-learn-15100`
- `sphinx-doc__sphinx-8269`

V02 cleaned:

- `matplotlib__matplotlib-13989`
- `pylint-dev__pylint-4970` (V01 unresolved)
- `pytest-dev__pytest-5809`
- `scikit-learn__scikit-learn-15100`
- `sphinx-doc__sphinx-8269`

V02 cleaned unresolved with patch: `astropy__astropy-12907` (wrong large rewrite vs V01 one-line fix).  
V02 empty: `django`, `requests`, `xarray`, `sympy`.

## Behavioral notes (cleaned collection)

| Metric | V01 | V02 |
|--------|-----|-----|
| Used `todo` | 0 / 10 | **10 / 10** |
| Touched gold source file | 7 / 10 | 6 / 10 |
| Non-empty source patch | — | 6 / 10 |
| Patch close to gold (Jaccard ≥ 0.3) | 0 / 10 | 2 / 10 |

## Interpretation

- After fixing patch collection, Todo neither clearly helps nor hurts official
  resolved count on this slice (**5 / 10** both), with a swap: gained pylint,
  lost astropy.
- Todo process goal is met (10 / 10 usage).
- Empty-patch cases remain the main room for improvement.
- Always smoke-check predictions for helper-file noise before trusting harness
  scores.
