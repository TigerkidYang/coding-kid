# Todo Discrimination Eval Slice

Purpose: measure whether Version 02's session `todo` tool improves **multi-step
goal-only** work versus Version 01. This slice is the primary Todo evidence.
Verified × 10 remains a SWE bugfix baseline only (tied 5/10); it does **not**
prove Todo value.

## Hard selection rules

Each task must satisfy all of:

1. **Goal-only prompt** — state the end state and deliverables; never number
   steps 1–N in the user message (that leaks decomposition).
2. **≥3 checkable deliverables** — e.g. fix several modules + CHANGELOG, or
   implement + tests + README.
3. **Single steps are easy** — solvable with `read` / `search` / `write` /
   `patch` / `execute`; no Glob/Grep/MCP/official Docker harness required.
4. **V01 Outcome fail first** — drop any task Version 01 already Outcome-passes.
5. **Local grading** — pytest and/or file checks only.

Explicitly excluded as Todo proof: Verified × 10 point fixes, prompts that
already contain a checklist, and single-file one-line bugs (e.g. code-001).

## Goal-only prompt template

```text
The project in the current directory needs: <overall goal>.

When finished, all of the following must be true:
- <deliverable A>
- <deliverable B>
- <deliverable C>
...

Constraints: <do not modify tests / deps / etc.>
Verify with: <local command>
```

## Dual metrics (same model, same tool budget)

| Metric | Meaning |
|--------|---------|
| **Outcome** | Deliverables present and local checks pass (pass/fail). |
| **Process** | Whether `todo` was used and maintained (V02 only; V01 = N/A). |

Process scoring (V02):

- `used_todo`: at least one `todo` tool call
- `todo_updates`: number of `todo` calls (≥2 preferred)
- `had_progress`: any item reached `completed`, or list ended non-empty with
  progress statuses
- `process_pass`: `used_todo` and (`todo_updates >= 2` or `had_progress`)

## Success bar (pre-registered)

- **V01**: Outcome low on the filtered slice (expect near 0 on multi-step
  goal-only anchors).
- **V02**: Outcome clearly above V01 on the same surviving tasks, **and**
  Process high (`process_pass` near all survivors).
- If V02 Outcome does not rise: conclude Todo is insufficient / budget still
  tight / other capabilities missing — not that the wrong tasks were chosen.

## Layout

```text
evals/v02-baseline/
  TODO_SLICE.md          # this protocol
  todo_slice/
    tasks.json           # manifest (goal-only prompts + grade specs)
    fixtures/            # starter trees (AgentBench + local multi-step)
    workspaces/          # per-run working copies
    run_todo_slice.py    # V01 archive / V02 runner + graders
    v01_report.json      # raw V01 results
    v02_report.json      # raw V02 results
    SCORECARD.md         # Outcome + Process comparison
```

## Run order

1. Assemble tasks under `todo_slice/` (goal-only + local graders).
2. Run Version 01 archive: `uv run python evals/v02-baseline/todo_slice/run_todo_slice.py --agent v01`
3. Keep only tasks with V01 `outcome_pass == false`.
4. Run current V02 on survivors: `--agent v02 --only-v01-fails`
5. Write `todo_slice/SCORECARD.md`. Do not treat Verified × 10 as Todo proof.
