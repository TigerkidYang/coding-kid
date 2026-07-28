# Version 02 Task-Decomposition Evaluation

Date: 2026-07-28  
Model: `openai/gpt-5.6-luna`  
Dataset: `SWE-bench/SWE-bench_Verified`  
Harness: official SWE-bench 4.1.0 Docker harness

## Result

The evaluation infrastructure worked, but the tested Version 02 scheduling
experiment did **not** demonstrate a reliable coding-outcome improvement.

| Version | Resolved | V2-only wins | V1-only regressions |
|---------|----------|--------------|---------------------|
| Version 01 | **1 / 10** | — | — |
| Version 02 scheduling experiment | **1 / 10** | **1** | **1** |

Resolved IDs:

- Version 01: `matplotlib__matplotlib-14623`
- Version 02: `sphinx-doc__sphinx-8120`

The predeclared success rule in `PROTOCOL.md` required Version 02 to gain at
least three resolved instances, produce at least three V2-only wins, and have
no more than one V1-only regression. The final result failed the first two
conditions.

## Frozen final set

`final_10_ids.json` was written before either final inference run. The set was
not changed after seeing Version 02 results.

Selection used previously unseen candidates with:

- at least one resolution among eight public agent runs;
- at most three gold source files;
- at most 50 changed gold source lines;
- a problem statement no longer than 3,000 characters.

Candidates were ordered by public resolve count descending, gold patch size
ascending, then instance ID.

## Process evidence

Version 02 used `todo` on all ten final instances. Its traces generally moved
from inspection to implementation sooner than Version 01, which spent the full
12 non-todo calls on investigation in most instances.

That process difference was not sufficient:

- Five Version 02 turns ended with lifecycle errors because a todo remained
  active or the model exceeded its step limit.
- Several patches implemented the apparent requirement but failed existing
  compatibility tests.
- The single V2-only Sphinx win showed the intended sequence: inspect locale
  loading, update the translation path order, then run focused tests.
- The Matplotlib regression shows that scheduling did not reliably preserve
  Version 01's existing wins.

Calling `todo`, producing a patch, or following the checklist was therefore not
counted as success unless the official harness resolved the instance.

## Calibration history

The calibration sets were deliberately excluded from the frozen final set.

| Calibration | V1 | V2 | What it showed |
|-------------|----|----|----------------|
| Initial moderate 8 | 0 / 8 | 1 / 8 | Initial tasks were mostly too difficult. |
| Existing baseline 10 | 5 / 10 | 5 / 10 | Scheduling changed behavior but not net outcome. |
| Easy unseen 4 | 0 / 4 | 1 / 4 | Lower difficulty exposed one V2-only win, but not a large effect. |
| Long-horizon Django 4 | 3 / 4 | 3 / 4 | A shared 24-call budget raised both versions equally; task tracking did not distinguish them. |
| Multi-requirement checkpoint 2 | 0 / 2 | 0 / 2 | Scheduling changed the trajectory, but the only patch passed just 2/4 fail-to-pass tests. |

Runtime-enforced scheduling variants were explored only on calibration data.
Because the frozen final result still tied and introduced a regression, those
experimental runtime constraints were reverted. The small session-scoped todo
implementation remains the Version 02 design.

The first long-horizon grading attempt incorrectly reported 0/4 for both
versions because Windows permission changes made `tests/runtests.py`
non-executable in the Linux harness. The prediction exporter now removes
mode-only diffs; regrading the unchanged substantive patches produced the
valid 3/4 tie above.

## Docker and network controls

All SWE-bench instance images were pulled with the explicit
`docker.1ms.run/...` prefix. Before every pull, `docker_images.py` verified:

- `docker.1ms.run` was configured as an allowed daemon mirror;
- Windows proxy bypass included that host;
- FlClash's active configuration routed Chinese IPs to a direct-only group;
- AliDNS resolved the mirror into the approved `101.227.21.0/24` range.

After each pull, the domestic tag was retagged to the official SWE-bench image
name and both tags were required to have the same Docker image ID. The harness
then reported that all required instance images already existed locally and
reused them. No Docker Hub fallback command is present in the evaluation
scripts.

## Interpretation

This evaluation is useful precisely because it did not manufacture a positive
result. It demonstrates that Version 02 currently adds visible task tracking,
but does not yet establish a reliable SWE-bench resolution improvement over
Version 01.

The official final result should be reported as a **tie with a paired swap**,
not as progress in coding correctness. Version 02's demonstrated gain remains
process-level task visibility and decomposition; stronger outcome claims are
not supported by this run.
