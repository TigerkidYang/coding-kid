# Version 13 Verification

Date: 2026-08-06

## Artifact and Environment

- Artifact: `output/v13-verification/coding_kid-0.1.0-py3-none-any.whl`
- Clean runtime: isolated Python 3.11 virtual environment
- Host terminal backend: Windows ConPTY through `pywinpty 3.x`
- Restricted backend: Docker Desktop with
  `python:3.11-slim-bookworm`
- Model-backed trial: not run because neither `OPENROUTER_API_KEY` nor
  `OPENROUTER_MODEL` was available in the verification environment

No SWE-bench run or paid batch evaluation was authorized or performed. No paid
model request was made, so verification spend was USD 0.00.

## Deterministic Results

- The full suite collected 398 tests: 397 passed and one Windows symlink test
  was skipped. Runtime was 173.74 seconds.
- Ruff lint and formatting checks passed over all 245 maintained Python files.
- Tests cover short completion, automatic yield without restart, explicit
  background work, incremental cursors, bounded head/tail output and complete
  temporary logs, expired IDs, limits, pruning, exit races, and process-tree
  cleanup.
- A real Windows Python REPL test preserved a Chinese/emoji variable across
  writes, survived Ctrl+C, accepted another command, and exited normally.
- Real Docker tests covered interactive workspace-write and read-only sessions,
  same-container checks, restricted writes, and container cleanup.
- Workflow tests cover Plan/Review read-only visibility, Implementation
  mutation, Cautious/Auto/Full Access decisions, independent write/check
  approval, metadata protection, checkpoints, cancellation, and rollback.
- Root/child tests prove that child Agents receive private session namespaces
  and that cancellation or child completion reclaims their process trees.
- CLI tests cover list, input, poll, check, interrupt, and stop. A Textual test
  pilot exercises the same operations and verifies status and notifications.

## Stress and Lifecycle Results

Ten real Docker rounds each started an interactive shell and a concurrent
non-interactive long command. Both received same-container checks and the
manager was then closed. Every round ended with zero labeled containers and
zero execution-session reader threads. The full suite additionally repeats
host process-tree cleanup and completion/control race cases.

Application shutdown removed complete host process trees, managed containers,
reader threads, and the manager-owned temporary log directory. A new manager
reports an old session ID as unknown or expired instead of claiming recovery.

## Packaging and Clean Installation

- The wheel is 734,794 bytes and contains 220 entries / 216 Python files.
- It includes 27 frozen V12 runtime files and the 28 living implementation
  modules. It excludes tests, research, `showcase/`, caches, bytecode, and logs.
- Wheel metadata pins `pywinpty>=3,<4` on Windows.
- The clean installation launched explicit V1-V13 from an unrelated Git
  directory. All 13 versions exited before a provider request; V13 is the
  default and the historical launchers retain their frozen behavior.

## Installed-Wheel Terminal Trials

The clean-installed CLI controlled a real ConPTY Python REPL entirely through
the public session commands. It listed the session, assigned and printed the
value `安装包终端🐯`, read incremental output, ran a separate bounded readiness
check that printed `installed-ready`, sent Ctrl+C, printed `after-interrupt` in
the same REPL, and stopped the session.

The clean-installed full-screen TUI was then launched through an outer ConPTY.
It rendered, accepted `/exit`, and shut down normally. The source-tree Textual
pilot provides deterministic coverage of list/input/check/interrupt/stop and
notification synchronization because automated raw-key injection into nested
Windows full-screen terminals is timing-sensitive.

A real interactive Docker shell printed Unicode output. Its health check ran
with `docker exec` in that exact continuing container and returned
`ready-evidence`; the shell and container then exited cleanly. After all
installed-wheel trials, the matching host-process count and managed-container
count were both zero.

## Remaining Live-Model Trial

The requested final minimal model-driven REPL, service-check, and interruption
recovery workflow could not be started without model credentials. This is an
environmental verification gap, not a skipped deterministic check or a known
implementation failure. When credentials are available, it remains the only
unexecuted completion item and must stay within the standing USD 1.00 limit.

## Outcome

The Version 13 implementation, deterministic suite, stress suite, packaging,
historical-version launches, and direct real-terminal scenarios pass. The
version remains unarchived and untagged pending the minimal live-model trial
and the user's explicit stage-completion confirmation.
