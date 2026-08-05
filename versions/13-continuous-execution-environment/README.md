# Coding Kid Version 13 — Continuous Execution Environment

This teaching checkpoint replaces separate one-shot foreground/background
process ownership with one bounded, application-owned execution-session system.

## Demonstrated Capability

- Short commands still return directly, while long foreground commands yield a
  stable session ID without restarting the process.
- Interactive Windows ConPTY and Unix PTY sessions retain their working
  directory, variables, virtual environment, and program state across later
  input, polling, and model turns.
- The `task` tool lists, polls, waits, writes, interrupts, stops, and runs an
  explicit bounded readiness check in the same host or continuing container.
- Output uses non-duplicating incremental cursors, bounded in-memory head/tail
  retention, and complete manager-owned temporary logs.
- Whole process trees, PTYs, reader threads, logs, and containers are reclaimed
  on natural exit, stop, child-Agent completion, cancellation, and application
  shutdown. Old process-local IDs clearly expire after restart.
- V10 turn control, V11 host/Docker sandbox boundaries, and V12 workflow,
  approval, checkpoint, and rollback rules govern every new action. Child
  Agents receive isolated private session managers.
- CLI and Textual TUI controls expose live session state, incremental output,
  input, health checks, Ctrl+C, stop, counts, and completion notifications
  without equating process liveness with service readiness.

Version 13 does not reconnect operating-system processes after application
restart, provide remote execution, infer readiness from arbitrary log text,
install dependencies, build sandbox images, or act as a general service
supervisor.

## Verification

- Root implementation: 398 collected tests, 397 passed and one Windows symlink
  test skipped; Ruff lint and format checks pass over 245 Python files.
- Standalone archive: 338 tests passed with one Windows symlink skip on Python
  3.11.2; Ruff lint and format checks passed over all 56 Python files. A Python
  3.13 compatibility run also passed after selecting its Unicode-safe basic
  REPL for ConPTY sessions.
- Ten real Docker concurrency/process-tree stress rounds ended with no managed
  containers or execution-session reader threads.
- The root wheel contains the complete frozen V12 runtime and clean-install
  V1-V13 launches from an unrelated Git directory all pass.
- Installed terminal trials pass continuing Unicode/emoji Python REPL input,
  Ctrl+C recovery, same-container HTTP readiness evidence, Cautious denial
  without process loss, explicit stop, and complete cleanup.
- Real `openai/gpt-5.6-luna` workflows reused one REPL across three model turns,
  checked and stopped one Docker HTTP service, and completed the Cautious
  approve/deny/continue/stop flow. All attempts remained conservatively below
  USD 0.75. No SWE-bench or paid batch evaluation ran.

## Setup and Run

Requirements are Python 3.11+, uv, Docker plus a pre-pulled image for restricted
sandbox modes, and provider credentials for live use. Windows interactive
sessions install the pinned `pywinpty` dependency automatically.

```powershell
uv sync --extra dev
uv run coding-kid --sandbox danger-full-access --approval full-access
uv run coding-kid --sandbox workspace-write --approval cautious
```

Use `/tasks`, `/task poll <id>`, `/task input <id> <text>`,
`/task interrupt <id>`, `/task check <id> <command>`, and `/task stop <id>` to
control execution sessions directly. Session selection continues to support
`--new`, `--continue`, `--resume`, `--list-sessions`, and `--delete-session`.

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

The deterministic suite uses fake providers. Local MCP and Docker fixtures do
not call OpenRouter.

## Git Checkpoint

Annotated tag: `version-13-continuous-execution-environment`.
