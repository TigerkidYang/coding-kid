# SWE-bench Verified × 10 — Coding Kid V02 vs V01

Date: 2026-07-25
Model: `openai/gpt-5.6-luna`
Agent: Coding Kid Version 02 (`todo` tool)
Dataset: same 10 instances as the Version 01 baseline

## Official harness

Version 01 (already scored): **5 / 10 resolved**.

Version 02 official harness: **not completed**.

Reason: with domestic `registry-mirrors` configured, pulls of
`swebench/sweb.eval.x86_64.*` failed (`ImageNotFound` / hung pull). Those cold
images are not served reliably by the public mirrors. Stopping here avoids
another large VPN download until you choose a path:

1. Temporarily disable mirrors / use VPN once, pull and **keep** images
   (`--cache_level instance`), or
2. Score only with behavioral metrics for this iteration, or
3. Run harness on a cloud host with direct Docker Hub access.

## Behavioral comparison (same slice, same model)

| Metric | V01 | V02 |
|--------|-----|-----|
| Used `todo` | 0 / 10 | **10 / 10** |
| Touched gold source file | **7 / 10** | 5 / 10 |
| Hit 12-tool budget | 5 / 10 | **10 / 10** |
| Non-empty collected source patch | 10 / 10 | 10 / 10 |
| Patch close to gold (Jaccard ≥ 0.3) | 0 / 10 | 0 / 10 |

### Per instance

| Instance | V01 gold | V01 tools | V02 gold | V02 tools | V02 todo calls |
|----------|----------|-----------|----------|-----------|----------------|
| `astropy__astropy-12907` | yes | 6 | yes | 12 | 3 |
| `django__django-15278` | no | 12 | no | 12 | 1 |
| `matplotlib__matplotlib-13989` | yes | 10 | no | 12 | 1 |
| `psf__requests-5414` | no | 12 | no | 12 | 1 |
| `pydata__xarray-2905` | yes | 12 | no | 12 | 2 |
| `pylint-dev__pylint-4970` | yes | 11 | yes | 12 | 3 |
| `pytest-dev__pytest-5809` | yes | 12 | yes | 12 | 2 |
| `scikit-learn__scikit-learn-15100` | yes | 7 | yes | 12 | 3 |
| `sphinx-doc__sphinx-8269` | yes | 9 | yes | 12 | 2 |
| `sympy__sympy-20590` | no | 12 | no | 12 | 1 |

## Interpretation

- Version 02 successfully teaches the model to **use the todo tool** on every
  instance in this slice.
- Todo calls count toward the 12-tool budget. V02 hit the budget on **all 10**
  tasks, and gold-file edits fell from 7 to 5. This is a concrete tradeoff to
  address (for example: exclude `todo` from the budget, raise the budget, or
  tighten prompt guidance to plan in fewer updates).
- Local host pytest remains an unreliable outcome signal on Windows; official
  resolved counts still require the Docker harness once image pulls work.

## Artifacts

- `v2_verified_10_report.json`
- `v2_verified_10_analysis.json`
- `v2_verified_10_predictions_source.jsonl`
- `v2_verified_10_run.log`
- `run_v2_verified_10.py`
- `recollect_v2_patches.py`
- `run_harness_v02_in_docker.sh`
- Failed harness attempt log under
  `logs/run_evaluation/coding_kid_v02_verified10/`
