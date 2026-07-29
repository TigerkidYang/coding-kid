# Coding Kid Version 03 — Context Assembly

This teaching checkpoint adds bounded, source-aware, session-stable model input
assembly to the Version 02 coding agent.

## Demonstrated Capability

- Captures one immutable runtime and project snapshot per terminal chat.
- Finds the nearest `.git` directory or worktree file.
- Loads non-empty `AGENTS.md` files from the project root to the current
  directory.
- Labels every project instruction with its absolute source path.
- Bounds combined instruction contents to 32 KiB with visible truncation.
- Injects project context into provider request copies without growing real
  conversation history.
- Re-renders current todo and recovery guidance for every model/tool step.
- Preserves the existing provider shape, tool loop, rollback, tool budget,
  empty-response recovery, and todo reconciliation behavior.

The paired six-task context evaluation passed at 6/6 process and 6/6 outcome,
above the Version 02 outcome of 4/6. The official SWE-bench Verified × 10
secondary regression check resolved 7/10 with no empty patches or harness
errors.

## Setup

Requirements:

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` environment variables for live use

```powershell
uv sync --extra dev
```

## Run

Start Coding Kid inside the project directory whose `AGENTS.md` instructions
should be loaded:

```powershell
uv run python -m coding_kid
```

Restart the process after changing an `AGENTS.md`; instructions are
intentionally stable within one chat.

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

The deterministic suite covers Git-root discovery, layered instruction
ordering and isolation, the 32 KiB budget, invalid UTF-8, read errors, session
stability, request-only injection, dynamic overlays, rollback, and existing
Version 02 behavior.

## Intentional Limits

This version does not implement global or override instructions, fallback
filenames, includes, conditional rules, dynamic reloading, arbitrary project
file injection, automatic compaction, token-window monitoring, long-term
memory, skills, plugins, MCP, persistent sessions, or provider abstraction.

## Git Checkpoint

Matching annotated tag: `version-03-context-assembly`.
