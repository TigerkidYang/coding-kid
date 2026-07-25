# Investigation: V02 0/10 vs V01 5/10

Date: 2026-07-26

## Verdict

The first official V02 score (**0 / 10**) was mostly an **evaluation artifact**,
not proof that Todo destroys capability.

Primary cause: `recollect_v2_patches.py` committed the helper file
`_swe_test.patch`, then deleted it, so every `model_patch` contained a hunk that
deletes `_swe_test.patch`. SWE-bench harness then failed `git apply`, fell back
with `--reject`, and logged:

```text
Reversed (or previously applied) patch detected!  Assuming -R.
```

That **reverse-applied** the real source fix. Tests failed even when the agent's
source edit was correct (for example pytest / sklearn matched V01).

V01 predictions never contained `_swe_test.patch`.

## Evidence

| Instance (V01 resolved) | V01 patch | Contaminated V02 patch | Cleaned V02 patch |
|-------------------------|-----------|------------------------|-------------------|
| pytest-5809 | +1/-1, 416 chars | includes `_swe_test` delete; harness -R | 416 chars, same as V01 |
| sklearn-15100 | +1/-4, 584 chars | includes `_swe_test` delete; harness -R | 584 chars, same as V01 |
| sphinx-8269 | small | contaminated | cleaned; Jaccard to gold = 1.0 |
| matplotlib-13989 | small | contaminated | cleaned; Jaccard to gold = 1.0 |
| astropy-12907 | one-line correct fix | contaminated + large wrong rewrite | still a different/wrong edit |

Harness logs for contaminated pytest/sklearn explicitly show apply failure and
`-R` reverse apply, while still reporting `patch_successfully_applied: True`.

## Secondary findings

- Todo was used on 10/10 (process goal OK).
- After cleaning, 4/10 are empty patches (django/requests/xarray/sympy) — real
  agent misses, same failure mode as some V01 empties.
- Astropy under V02 still looks like a genuine wrong edit (large rewrite vs
  V01's one-line `_cstack` fix), independent of collection noise.

## Fix

1. Do not `git add` / commit `_swe_test.patch` when collecting agent diffs.
2. Strip any leftover `_swe_test.patch` hunks from collected patches.
3. Re-score cleaned V02 predictions with local images
   (`coding_kid_v02_verified10_clean`).

## Lesson for the project

Before trusting an official score, smoke-check predictions:

- no helper files in `model_patch`
- `git apply` on a clean checkout succeeds without `-R`
- compare patch size to V01 on previously resolved IDs
