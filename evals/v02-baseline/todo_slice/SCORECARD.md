# Todo Discrimination Scorecard

Model: `openai/gpt-5.6-luna`

Primary evidence for Version 02 Todo. Verified × 10 is not used here.

## Protocol

- Goal-only prompts (no numbered step lists in the user message).
- Dual metrics: Outcome (local checks) + Process (todo usage, V02).
- Slice filtered to tasks Version 01 failed on Outcome.

## Results

| Task | V01 Outcome | V02 Outcome | V02 Process | V02 todo_calls | Notes |
|------|-------------|-------------|-------------|----------------|-------|
| multi-003 | FAIL | FAIL | PASS | 2 | {"require_file": "CHANGELOG.md", "ok": false} |
| multi-006 | FAIL | FAIL | PASS | 2 | {"require_file": "CHANGELOG.md", "ok": false} |
| multi-007 | FAIL | FAIL | PASS | 2 | {"require_file": "CHANGELOG.md", "ok": false} |
| multi-009 | FAIL | FAIL | PASS | 1 | {"require_file": "CHANGELOG.md", "ok": false} |
| multi-010 | FAIL | FAIL | PASS | 2 | {"require_file": "CHANGELOG.md", "ok": false} |
| multi-012 | FAIL | FAIL | PASS | 1 | {"require_file": "CHANGELOG.md", "ok": false} |

## Summary

- Survivor tasks (V01 Outcome fail filter applied for V02 run): **6**
- V01 Outcome on survivors: **0/6** (should be 0 if filter held)
- V02 Outcome on survivors: **0/6**
- V02 Process pass: **6/6**

## Verdict

**Process improved; Outcome did not.**

- V02 consistently called `todo` on every survivor (Process **6/6**).
- Outcome stayed **0/6**, same as V01. Failures cluster on missing wrap-up
  files (especially `CHANGELOG.md`) after code fixes — the 12 file/shell tool
  budget is still exhausted before documentation deliverables.
- Pre-registered reading: Todo alone is not enough here; budget pressure (and
  possibly stronger wrap-up discipline) remains the binding constraint. Do not
  treat Verified × 10 as counter-evidence or as Todo proof.

## Verdict rule

- Todo looks helpful if V02 Outcome >> V01 and Process is high.
- If Outcome stays flat, Todo alone is not enough (budget / other skills).

## Full-slice V01 gate

Dropped after V01 (already Outcome-pass; cannot prove Todo gap): multi-001, multi-002, multi-004, multi-005, multi-008, multi-011
