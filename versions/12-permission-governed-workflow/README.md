# Coding Kid Version 12 — Permission-Governed Workflow

This teaching checkpoint adds explicit user authorization and recoverable stage
changes above Version 11's fail-closed sandbox.

## Demonstrated Capability

- Independent `plan`, `implementation`, and `review` collaboration modes;
  `cautious`, `auto`, and `full-access` approval policies; and the unchanged
  read-only/workspace-write/danger-full-access sandbox axis.
- Runtime tool filtering plus dispatch-time mode enforcement prevents hidden
  mutation calls in Plan and Review.
- One application-owned broker gates writes, commands, deletion, background
  work, child Agents, and MCP before `ToolStarted`. Prompts support approve once,
  conservative process grants, denial feedback, and abort.
- Structured Plan questions and explicit plan approval can retain or clear the
  model-visible context before Implementation.
- Protected, bounded checkpoints preserve pre-stage dirty content, track stage
  changes, show bounded review diffs, and refuse rollback over external edits.
- Root and child effects share approval and serialization. Pending approval is
  cancellable; grants do not persist, while mode, approved plan, checkpoint,
  and complete retained terminal-turn evidence do.

Version 12 does not provide persistent/remote policy, enterprise distribution,
automatic safety classifiers, worktree isolation, rollback for ignored or
project-external effects, remote MCP rollback, or a general workflow DSL.

## Verification

- Root implementation: 384 collected tests, 383 passed and one Windows symlink
  test skipped; Ruff lint and format checks pass.
- Standalone archive: 328 collected tests, 327 passed and the same Windows
  symlink test skipped; Ruff lint and format checks pass.
- Ten repeated approval, concurrency, rollback-conflict, child-routing,
  background-cleanup, and parallel-read stress rounds pass.
- Root wheel: 193 entries / 189 Python files, complete frozen V11 runtime, and
  clean-install V1-V12 launches from an unrelated directory.
- Installed-wheel `openai/gpt-5.6-luna` pseudo-terminal trials pass Plan,
  Cautious allow/deny, Review/Accept, Auto rollback, read-only under Full Access,
  approval interruption, child approval routing, background cleanup, and
  checkpoint/grant resume. At most 18 short responses kept estimated spend below
  USD 0.10. No SWE-bench or paid batch evaluation ran.

## Setup and Run

Requirements are Python 3.11+, uv, Docker plus a pre-pulled image for restricted
sandbox modes, and provider credentials for live use.

```powershell
uv sync --extra dev
uv run coding-kid --mode plan --approval cautious
uv run coding-kid --mode implementation --approval auto
uv run coding-kid --sandbox read-only --approval full-access
```

Use `/permissions`, `/mode`, `/changes`, and `/sandbox` to inspect or control the
separate layers. Session selection supports `--new`, `--continue`, `--resume`,
`--list-sessions`, and `--delete-session`.

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

The deterministic suite uses fake providers. Local MCP fixture tests do not call
OpenRouter.

## Git Checkpoint

Annotated tag: `version-12-permission-governed-workflow`.
