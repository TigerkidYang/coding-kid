# Coding Kid Version 08 — Background Tasks

This teaching checkpoint adds explicit, process-local background shell tasks to
Version 07 without changing the synchronous Agent loop. One application-owned
manager keeps tasks alive across user turns and binds `execute` and `task` into
the same per-turn registry as Skills, Plugins, and MCP tools.

## Demonstrated Capability

- `execute(command, background)` preserves the bounded two-minute foreground
  path and starts non-interactive background work only when explicitly asked.
- Background launch immediately returns a stable random `task_<12 hex>` ID.
- `task` provides bounded `list`, `poll`, cancellable `wait`, and idempotent
  process-tree `stop` operations with `running`, `completed`, `failed`, and
  `stopped` states.
- Tasks retain bounded stdout and stderr, completion events, durations, exit
  codes, truncation evidence, and a dynamic model-visible summary.
- The plain CLI and Streaming TUI expose `/tasks`, `/task stop <id>`, lifecycle
  notifications, and the current running count without waking the model.
- Failed or interrupted turns roll back conversation and todo state while an
  already-started background process remains discoverable.
- Shutdown stops every running tree and joins readers before MCP and session
  resources close. Windows shells start suspended, enter a kill-on-close Job
  Object, then resume; termination also retains `taskkill /T`.

Tasks do not survive a Coding Kid process restart and never enter persistent
sessions or long-term memory. Waiting proves only process completion, not server
readiness; readiness still requires output evidence or a health check.

## Verification

- Root implementation: **254 deterministic tests** plus Ruff lint and format
  checks.
- Standalone archive: **215 deterministic tests** plus Ruff lint and format
  checks.
- Ten mixed concurrency rounds and ten parent/child stop rounds passed without
  state regression, duplicate terminal events, deadlock, lingering threads,
  processes, or a delayed sentinel.
- The final root wheel contained 100 files / 96 Python files, including frozen
  V01–V07 and living V08, and launched V1–V8 plus default V08 from a clean
  unrelated directory.
- A real `openai/gpt-5.6-luna` run backgrounded a Unicode worker, performed
  independent work before waiting, captured separate stdout/stderr, and stopped
  a parent/child process tree. The instrumented final run used 11,820 input
  tokens, 547 output tokens, and USD 0.00116478.
- No SWE-bench or paid batch evaluation was run.

## Setup

Requirements:

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` for live use

```powershell
uv sync --extra dev
```

## Run

Start the standalone Version 08 agent inside the project it should operate on:

```powershell
uv run coding-kid
```

Session selection remains available through `--new`, `--continue`, `--resume`,
`--list-sessions`, and `--delete-session`. Use `/tasks` to inspect process-local
background work and `/task stop <id>` to stop it without a model call.

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

The tests use fake providers and local processes; they do not call OpenRouter.

## Intentional Limits

Version 08 does not provide automatic backgrounding, autonomous model wakeups,
task persistence, remote jobs, scheduled work, PTY/stdin interaction, readiness
guessing, multi-agent workflows, sandboxing, or approvals. Built-in and MCP
tools still inherit the current user's permissions.

The cross-version launcher remains an unnumbered root-project facility. This
archive does not recursively carry the V1–V7 bundled runtimes.

## Git Checkpoint

Annotated tag: `version-08-background-tasks`.
