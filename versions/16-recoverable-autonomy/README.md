# Coding Kid Version 16 — Recoverable Autonomy

This standalone teaching checkpoint keeps Coding Kid's explicit `execute +
task` architecture while making recovery proportional to the trust boundary.

Version 16 adds:

- `required`, `best-effort`, and `off` checkpoint policies with honest
  `full`, `scoped`, or `none` recovery coverage;
- explicit partial rollback when unknown side effects prevent a complete
  application rollback;
- an external-isolation bypass preset for disposable containers or VMs;
- atomic, bounded, multi-file `apply_patch` and a shared `diff` view;
- recoverable TODO guidance and controlled incomplete results at resource
  boundaries.

It intentionally does not merge `execute` and `task`, add benchmark-specific
prompts, or automatically undo ordinary test failures.

## Run

```powershell
uv sync --extra dev
uv run coding-kid
```

The safe default is cautious approval with required checkpoints. In a trusted
external container or VM only, the explicit bypass preset is available:

```powershell
uv run coding-kid --dangerously-bypass-approvals-and-sandbox
```

## Test

```powershell
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
```

The independently verified archive results are recorded in the root project's
`docs/reports/v16-verification.md`.

This archive passes 410 tests with two Windows symlink skips, Ruff check and
format check over 62 Python files, a 35-entry wheel inspection, and clean
Python 3.11 installation and launch from an unrelated directory.

Original annotated Git tag: `version-16-recoverable-autonomy`.

Maintenance tag `version-16-recoverable-autonomy-fix1` additionally normalizes
empty provider messages before protocol replay and translates null-collection
Responses SDK failures into observable, bounded provider retries. The original
tag remains unchanged.
