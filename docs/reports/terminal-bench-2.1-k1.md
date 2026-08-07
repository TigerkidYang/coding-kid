# Terminal-Bench 2.1 k=1 Evaluation

## Result

Coding Kid V15 with `gpt-5.6-luna` and `reasoning.effort=max` completed all 89
Terminal-Bench 2.1 tasks with one valid trial per task:

- Passed: 50
- Agent timeout: 9
- Completed with verifier reward 0: 30
- Infrastructure failures in the final result: 0
- Exit 137: 0
- Score: **50 / 89 = 56.18%**

This is a k=1 result. It should not be presented as a directly comparable
replacement for a leaderboard result that averages multiple trials or reports
pass@k. It is a reproducible measurement of this project and model pairing,
not a model-only score.

## Protocol

- Dataset: official Terminal-Bench 2.1, 89 tasks.
- Agent: the living Coding Kid V15 runtime after the fixes listed below.
- Model: `gpt-5.6-luna` through the supplied OpenAI-compatible Responses API.
- Reasoning: max effort.
- Sampling: one valid result per task; diagnostic and aborted runs are excluded.
- Execution: one Harbor trial per Cloudflare `standard-4` Container, with the
  official verifier running inside the trial.
- Concurrency: began at 16, backed off through 12, 8, and 4 when Cloudflare or
  the model endpoint became unstable, then returned to forced 16 for the tail.
- Run duration: 2026-08-06 23:55:44 UTC through 2026-08-07 04:10:32 UTC,
  including infrastructure retries and two targeted supplemental tasks.

`AgentTimeoutError` is an official zero and remains in the score. Container
start errors, status-query errors, model-transport failures, and Cloudflare 524
responses were retried and never converted into ability zeros. The run was not
declared complete until all 89 tasks had valid verifier outcomes.

## Before-and-after comparison

The first complete k=1 run scored 45 / 89 (50.56%):

- 45 passes
- 22 Agent timeouts
- 13 exit-137 failures
- 9 other verifier zeros

After the engineering fixes and a fresh full run, the result became 50 / 89
(56.18%):

- Five additional passes
- A 5.62 percentage-point score increase
- Agent timeouts reduced from 22 to 9
- Exit 137 reduced from 13 to 0

The increase in ordinary verifier-zero results, from 9 to 30, is expected: the
fixed runtime now reaches the verifier instead of dying from resource pressure,
missing Git, or timeout-heavy tool detours. These are valid capability failures
rather than masked engineering failures.

## Problems exposed and fixes

### Unbounded inspection caused exit 137

Broad file searches and binary reads could consume the task container's
resources. Commit `b0c70eb` bounds search by file count, total bytes, per-file
bytes, and result count; makes reads binary-aware and bounded; hardens POSIX
shell detection; and handles missing worktree executables. The final run had no
exit-137 result.

### Irrelevant or unusable tools distorted tool selection

The model was shown plan-only tools in implementation mode, empty task/Agent
management surfaces, unavailable Brave search, and a worktree default that
could not work outside Git. Commit `221a708` makes the visible tool surface
mode-, state-, credential-, and repository-aware. Commit `5361d00` removes a
long negative command-guidance block that caused Luna to avoid `execute`.

Bounded final log tails directly show `execute` in 63 of 89 tasks, with at
least 654 execute calls, and `write` in 36 tasks, with at least 49 writes. These
are lower bounds because the retained tails omit early calls.

### Checkpoints accidentally required Git

Some official task environments do not contain `git`. The checkpoint manager
therefore prevented every side-effecting tool before the model could write or
execute. Commit `1243538` adds a bounded filesystem snapshot fallback for
missing Git and non-Git projects while preserving rollback and conflict
detection. The directly affected `break-filter-js-from-html` preflight then
used execute/write, passed its local check, and received reward 1.0.

### Cloudflare hid long model responses behind 120-second 524s

The benchmark CLI sends non-streaming Responses requests. A normal reverse
proxy could not emit bytes while waiting for the JSON response, so long max-
effort requests repeatedly hit Cloudflare's 120-second origin timeout.
`heartbeat_proxy.py` now sends a chunked JSON response with legal leading
whitespace keepalives every 15 seconds, then appends the unchanged upstream
JSON. Streaming requests use chunked padded SSE heartbeats. After this change,
`regex-chess` completed in about 5 minutes 43 seconds without a 524, and both
previously exhausted tasks obtained valid verifier results.

### The batch runner needed durable recovery

The scheduler persists every transition, resumes completed work, separates
infrastructure retries from ability results, stops completed containers, and
supports targeted supplements. A bounded retry around Windows atomic state
replacement fixed an observed file-sharing race. The same state survived
several concurrency changes and scheduler restarts without repeating any valid
trial.

## Remaining capability failures

The nine official AgentTimeout results were:

- `build-cython-ext`
- `configure-git-webserver`
- `extract-elf`
- `gcode-to-text`
- `gpt2-codegolf`
- `largest-eigenval`
- `qemu-alpine-ssh`
- `raman-fitting`
- `sqlite-with-gcov`

These point to the next highest-value optimization area: faster early
environment diagnosis, tighter step budgeting, better management of long
commands, and less exploratory work before producing the required artifact.

Thirty tasks ran to a valid verifier result but scored zero. Those are now the
cleanest task-level dataset for capability analysis because resource deaths,
missing-Git failures, and transport failures have been removed from the final
classification. A future change should use a fixed subset of these failures for
development and reserve a fresh full run for confirmation, avoiding benchmark
overfitting.

## Verification

- Final Version 15 root suite: 448 passed, with one Windows symlink test skipped.
- Targeted checkpoint/tool/workflow tests and Ruff over changed maintained
  source passed.
- Cloudflare container rollout: version 26, 7/7 healthy, 0 failed before the
  final run.
- Final state: 89 completed, 0 pending, 0 running, 0 retry-pending, 0
  infrastructure failures.

Raw generated run state and logs remain locally under the ignored
`evals/terminal-bench-2-1/cloudflare-runner/runs/` directory. They are not
committed because they are large operational artifacts.
