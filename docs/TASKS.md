# Tasks

## Current Core Version: 13 — Continuous Execution Environment

Completion status: implementation and non-model verification complete; final
live-model verification is unavailable because the current environment has no
model credentials. The user selected the
supplementary improvement "Rich, continuous execution environment," approved
the implementation plan, and explicitly delegated implementation,
deterministic verification, and bounded real installed-wheel terminal
verification to the assistant.

### Goal

Replace one-shot foreground/background command ownership with one bounded,
application-owned execution-session system. A command that outlives its initial
wait remains addressable; an interactive session can accept later input,
interrupts, and health checks without being restarted.

### Included Scope

- One execution-session manager for short commands, yielded commands, explicit
  background work, interactive terminals, incremental output, and cleanup.
- `execute` options for `interactive` and `yield_time_ms`; long foreground work
  automatically yields a stable session ID.
- `task` actions for list, poll, wait, write, interrupt, stop, and an explicitly
  evidenced same-environment health check.
- Windows ConPTY and Unix PTY support with Unicode, newline, Ctrl+C, and
  whole-process-tree lifecycle handling.
- Bounded memory/log retention, session limits, deterministic pruning, and
  process-local expired-session behavior after restart.
- Predictable host and Docker behavior under the V11 sandbox, including
  continuing restricted containers and in-container health checks.
- V12 workflow/approval/checkpoint enforcement for every new action, scoped
  child-Agent ownership, CLI/TUI controls, state, and notifications.
- Frozen V12 runtime plus installed V1-V13 selection.

### Excluded Scope

- Reconnecting operating-system processes after Coding Kid restarts.
- Remote execution environments, browser or GUI automation, automatic package
  installation, automatic image builds, or a general service supervisor.
- Inferring readiness merely because a process is alive or a log line looks
  promising.
- Isolated Agent worktrees, persistent permission grants, or a new benchmark.

### Completion Criteria

- The same Python/shell terminal accepts multiple inputs across model turns,
  preserves state, handles Unicode, and remains usable after Ctrl+C.
- A long command yields without restarting, exposes non-duplicated incremental
  output, and is safely interruptible/stoppable with complete descendant and
  container cleanup.
- Service readiness is demonstrated by a bounded check in the same execution
  environment and remains distinct from liveness.
- Plan/Implementation/Review, Cautious/Auto/Full Access, and all three sandbox
  modes retain their independent guarantees for start, write, check,
  interrupt, and stop operations.
- Root/child ownership, cancellation, checkpointing, CLI/TUI presentation,
  session limits, restart expiry, and failure races are deterministically
  covered.
- Pytest, Ruff, ten cleanup/concurrency stress rounds, wheel inspection,
  V12 source fidelity, clean-install V1-V13 launches, and real terminal/TUI
  trials pass. Any live model verification stays below the standing USD 1.00
  task allowance; SWE-bench and paid batch evaluation do not run.

### Implementation Sequence

1. Freeze V12, advance the launcher, and record the Version 13 boundary.
2. Unify non-interactive foreground/background lifecycle and output handling.
3. Add portable PTY sessions and continuing input/interrupt support.
4. Extend tool, CLI/TUI, notifications, sandbox, health-check, permission, and
   child-Agent integrations.
5. Complete deterministic, stress, packaging, clean-install, and bounded real
   terminal verification; update durable architecture and decisions.

The version is archived and tagged only after the user explicitly confirms
stage completion.

### Verification Record

- Full suite: 397 passed, one Windows symlink test skipped.
- Ruff lint and formatting: passed over 245 Python files.
- Ten real Docker concurrency/cleanup rounds: passed with no residual
  containers or reader threads.
- Wheel inspection, clean installation, and explicit V1-V13 launches: passed.
- Real host ConPTY, installed CLI, installed full-screen TUI launch/exit, and
  continuing Docker terminal/check/cleanup trials: passed.
- Minimal paid model workflow: not run because `OPENROUTER_API_KEY` and
  `OPENROUTER_MODEL` are unavailable; spend is USD 0.00.

See `docs/reports/v13-live-verification.md` for the evidence and remaining
completion gate.
