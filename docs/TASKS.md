# Tasks

## Current Core Version: 16 — Recoverable Autonomy

Completion status: complete and archived under
`versions/16-recoverable-autonomy/` with annotated tag
`version-16-recoverable-autonomy`.
The user approved and delegated the complete implementation, deterministic
verification, packaging, and bounded real terminal verification on 2026-08-07.

### Goal

Keep the explicit teaching architecture while making recovery proportional to
the trust boundary, adding efficient reviewable multi-file editing, and letting
the model treat todos and recoverable failures as guidance rather than fatal
workflow gates.

### Included Scope

- Required, best-effort, and disabled checkpoint policies, plus one explicit
  externally isolated bypass preset.
- Full-stage or path-scoped recovery coverage with honest partial rollback,
  conflict detection, review, and status reporting.
- Atomic validated multi-file `apply_patch`, a model-visible `diff`, and a more
  useful exact-fragment `patch`.
- Optional todo use, soft reconciliation for active work, incomplete-plan
  completion evidence, and provider-output normalization.
- Frozen V15 runtime plus installed V1-V16 selection with V16 as the default.

### Excluded Scope

- Merging `execute` and `task`, adopting Codex Code Mode, or redesigning the
  synchronous teaching loop.
- Model- or benchmark-task-specific prompts and any new paid benchmark run.
- Automatic rollback after ordinary tool, test, or task-completion failure.
- Changes to completed archives or historical tags.

### Completion Criteria

- Recovery behavior matches each policy and never overstates coverage.
- Large or unusual non-Git content cannot block best-effort or disabled work;
  required mode continues to fail closed.
- `apply_patch` validates a whole bounded patch before mutation and `diff`
  reports the best available attributable evidence.
- Pending or active todos cannot crash an otherwise valid turn.
- Root and standalone regressions, Ruff, stress, wheel inspection, clean
  installation, V1-V16 launches, and bounded real CLI/TUI trials pass.

### Implementation Sequence

1. Freeze V15 and add recovery-policy configuration and manifests.
2. Add scoped recovery, partial rollback, bypass operation, and UI evidence.
3. Add `apply_patch`, `diff`, and improved exact replacement.
4. Relax todo completion, normalize provider output, and verify loop recovery.
5. Run deterministic, stress, packaging, and bounded live verification before
   creating the standalone V16 archive.

All five implementation steps, root/live verification, and independent archive
verification are complete. See `docs/reports/v16-verification.md`.
