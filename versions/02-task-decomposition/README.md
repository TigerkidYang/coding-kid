# Coding Kid Version 02 — Task Decomposition

This is the independently runnable teaching checkpoint for Coding Kid Version
02. It keeps the synchronous terminal coding agent from Version 01 and adds a
session-scoped `todo` tool for task decomposition and progress tracking.

## Demonstrated Capability

- Replace-based todo lists with `pending`, `in_progress`, and `completed`
  statuses.
- At most 20 items, 200 characters per item, and one `in_progress` item.
- Process-local state that rolls back with failed or interrupted CLI turns.
- Current todo injection into model instructions.
- One reconciliation retry before accepting a final answer with unfinished
  work.
- A separate file/shell tool-call budget so todo updates do not consume the
  work budget.

Version 02 passed 52 automated tests, Ruff lint and formatting checks, and a
live multi-step todo smoke. Its official SWE-bench Verified × 10 score was
5/10, matching Version 01. A goal-only task-decomposition slice showed todo
process use on 6/6 survivor tasks, while outcome remained 0/6.

## Setup

```powershell
uv sync --extra dev
```

Set `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in the environment.

## Run

```powershell
uv run python -m coding_kid
```

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

## Git Checkpoint

The matching annotated tag is `version-02-task-decomposition`.

