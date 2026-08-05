# Version 13 Verification

Date: 2026-08-06

## Artifact and Environment

- Artifact: `output/v13-verification/coding_kid-0.1.0-py3-none-any.whl`
- Clean runtime: isolated Python 3.11 virtual environment
- Host terminal backend: Windows ConPTY through `pywinpty 3.x`
- Restricted backend: Docker Desktop with
  `python:3.11-slim-bookworm`
- Model-backed trial: `openai/gpt-5.6-luna`, using the user-level Windows
  environment configuration injected into the isolated verification process

No SWE-bench run or paid batch evaluation was authorized or performed.

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

## Live-Model Trials

The initial environment inspection checked only process-level variables and
incorrectly concluded that model credentials were unavailable. The configured
key and model were present as Windows user-level environment variables. They
were injected into isolated child processes without printing or persisting the
key, and the earlier conclusion was corrected.

### Continuing host REPL

Across three separate user/model turns, the installed V13 CLI and
`openai/gpt-5.6-luna` operated one session, `task_2bd82c9dd9de`. The model:

1. started one interactive Python REPL and printed `连续终端🐯`;
2. found and reused that session, produced the expected `ValueError`, and then
   printed the retained Unicode value; and
3. sent Ctrl+C, observed `KeyboardInterrupt`, printed
   `continued-after-ctrl-c 连续终端🐯`, and exited the same REPL.

The durable transcript contains the unchanged session ID, traceback, retained
value, interrupt evidence, recovery output, and final process exit. No command
was silently restarted.

### Same-container service check

Under `workspace-write`, the model started a background HTTP server in the
continuing Docker container. Its `task check` result records
`readiness_check: explicit`, exit code 0, and stdout `200`. The subsequent
server log contains `GET / HTTP/1.1\" 200`. The model then stopped the session;
the final managed-container count was zero.

### Cautious denial without process loss

In Cautious mode, the user approved the REPL start and initial assignment
`cautious_value = 41`, then denied a later write of `99`. The durable record
contains `User denied task` with the supplied feedback. The model listed the
same still-running session, obtained separate approval for a new input, and
observed `cautious-still-alive 42`, proving that denial neither killed the
process nor changed its state. A final, separate stop approval reclaimed it.

### Driver corrections and usage bound

Two verification-driver mistakes were rejected rather than counted as passes:

- A nested ConPTY driver initially searched for a completion marker that was
  also visible in its own prompt. The corrected check showed that raw-key
  injection had not submitted the TUI input, so the process was stopped and the
  reliable redirected plain CLI was used for model turns.
- A literal emoji in redirected Windows stdin arrived as invalid surrogate
  characters. The prompt was changed to ASCII and the model constructed the
  same Unicode value inside the real ConPTY REPL. Direct ConPTY Unicode and
  emoji behavior was already covered by the installed and deterministic trials.

Across successful trials and these bounded exploratory attempts, durable logs
contain 54 completed model responses in 13 committed user turns plus one
terminal turn. At most two started transient responses were not retained. The
largest final request contained 5,918 input tokens. Using the
[OpenRouter model page](https://openrouter.ai/openai/gpt-5.6-luna-20260709)'s
listed standard price ceiling and conservatively allowing for the short
intermediate outputs, estimated total spend remained below USD 0.75, within the
USD 1.00 task allowance. Exact per-request cost is not persisted.

## Outcome

All Version 13 implementation, deterministic, stress, packaging,
historical-version, direct terminal, and live-model completion criteria pass.
The version remains unarchived and untagged pending the user's explicit
stage-completion confirmation.
