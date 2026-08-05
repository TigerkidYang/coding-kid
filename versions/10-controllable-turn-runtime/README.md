# Coding Kid Version 10 — Controllable Turn Runtime

This teaching checkpoint replaces the implicit collection of loop branches in
Version 09 with an explicit, bounded Turn/Step control runtime while preserving
the synchronous root model/tool loop.

## Demonstrated Capability

- Typed phases and transition reasons describe provider work, tool scheduling,
  recovery, steering, interruption, budgets, stalls, and terminal outcomes.
- The full-screen TUI accepts up to eight active-turn inputs in FIFO order and
  distinguishes soft steering from an Escape hard interrupt.
- Complete model/tool protocol rounds are evidence boundaries: completed tool
  effects and their matched outputs survive interruption, failure, and
  persistent-session resume, while incomplete streams are discarded.
- Cancellation propagates into provider waits, foreground process trees,
  background/Agent waits, and tool scheduling, retaining bounded partial
  evidence where applicable.
- Provider retry and output-limit recovery are explicit and bounded; repeated
  identical actions trigger a circuit breaker instead of looping indefinitely.
- Consecutive built-in reads and searches may overlap with at most four workers
  while mutating, stateful, and externally supplied tools remain exclusive.
- Structured control events make queue transitions, retries, recovery, budgets,
  stalls, stream resets, and the single terminal outcome observable to clients.

Version 10 does not add a sandbox or approval policy, workflow DSL, durable
in-flight steps, remote workers, arbitrary lifecycle hooks, autonomous model
wakeups, speculative streaming tool starts, or general side-effect rollback.

## Verification

- Root implementation: **289 deterministic tests** plus Ruff lint and format
  checks.
- Standalone archive: **244 deterministic tests** plus Ruff lint and format
  checks. Its launcher-specific test is omitted because this checkpoint starts
  V10 directly.
- Ten rounds of safe overlap, exclusive barriers, FIFO steering, hard
  interruption, and foreground process-tree cleanup passed without deadlock,
  leaked workers, or delayed sentinels.
- The final root wheel contains 143 files, frozen V01–V09 and living V10, with
  no tests, evaluations, `showcase/`, logs, or caches. A clean installation
  launches V1–V10 plus default V10 from an unrelated directory.
- Real installed-wheel `openai/gpt-5.6-luna` TUI trials passed soft steering,
  FIFO continuation order, hard interruption, process cleanup, persistent
  resume, and retained completed-write recall without another tool call.
- The eight paid responses cost conservatively less than USD 0.02. No SWE-bench
  or paid batch evaluation was run.

## Setup

Requirements:

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` for live use

```powershell
uv sync --extra dev
```

## Run

Start the standalone Version 10 Agent inside the project it should operate on:

```powershell
uv run coding-kid
```

Session selection supports `--new`, `--continue`, `--resume`,
`--list-sessions`, and `--delete-session`. While a turn is active, submit a new
message to steer it at the next control boundary or press Escape for a hard
interrupt.

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

The deterministic tests use fake providers and local processes; they do not
call OpenRouter.

## Git Checkpoint

Annotated tag: `version-10-controllable-turn-runtime`.
