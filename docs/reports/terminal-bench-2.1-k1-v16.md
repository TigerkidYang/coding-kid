# Terminal-Bench 2.1 k=1 Evaluation — Version 16 Fix 4

## Result

Coding Kid Version 16 maintenance fix 4, paired with `gpt-5.6-luna` at max
reasoning effort, completed one valid Terminal-Bench 2.1 trial for all 89 tasks:

- Passed: 61
- Zero reward after an Agent time boundary: 12
- Other completed verifier-zero results: 16
- Infrastructure failures in the final result: 0
- Score: **61 / 89 = 68.54%**

Three additional passing tasks reached an Agent time boundary only after they
had produced verifier-passing artifacts. Terminal-Bench scores their reward,
so they are included in the 61 passes rather than the 12 timeout zeros.

This is a k=1 measurement of one Agent/model pairing, not a pass@5 result or a
model-only score. Codex's published 75.7% result used at least five trajectories
per task, so the 7.2-point difference must not be interpreted as a deterministic
Agent-only gap.

## Protocol and integrity

- Dataset: official Terminal-Bench 2.1, 89 tasks.
- Agent version in every final trajectory:
  `v16-explicit-maintenance-fix4`.
- Model: `gpt-5.6-luna` through the supplied OpenAI-compatible Responses API.
- Reasoning effort: max.
- Sampling: one valid ability result per task; infrastructure-only attempts
  were excluded rather than converted to reward zero.
- Execution: Harbor trials in externally isolated Cloudflare containers with
  application checkpointing disabled, matching the intended V16 bypass mode.
- Valid run window: 2026-08-08 11:02:11 UTC through 16:21:50 UTC, including
  infrastructure recovery and the two-task transport supplement.

The run initially tested concurrency 8, 12, and 16. The 16-way cohort was
invalidated as a whole after synchronized endpoint failures; both its apparent
passes and failures were discarded. Stable work continued at 8 and then 12.
A later 23-second quick-tunnel outage returned HTTP 1033, so all 12 exposed
tasks were reset together, including a task that had appeared to pass. This
cohort-based policy avoids selectively retaining favorable outcomes.

At 87 valid results, only `regex-chess` and `train-fasttext` remained excluded
for exhausted model-transport failures. They were reset together for an
infrastructure-only supplement. `regex-chess` then passed. `train-fasttext`
ran normally for the full Harbor 1800-second installed-Agent command boundary
and was counted as an ability timeout, not retried again.

The final state is 89 completed, zero pending/running/retry-pending, and zero
infrastructure failures. Attempt distribution is 80 tasks at attempt 1, six at
attempt 2, two at attempt 3, and one at attempt 5. These attempt numbers reflect
transport or platform recovery, not repeated sampling after a valid reward.

## Comparison with Version 15

The prior V15 k=1 result was 50/89 (56.18%). Under the same dataset, model, and
reasoning effort, V16 fix 4 reached 61/89 (68.54%):

- 11 additional passing tasks;
- a 12.36 percentage-point increase;
- 90.5% of the published Codex + Luna point estimate, while retaining the
  important k=1 versus multi-trajectory caveat.

The improvement cannot be attributed only to V16's headline features. Fix 4
also repaired truncated non-streaming Responses JSON and the evaluation path
was hardened against long-response proxy failures. The result therefore
measures the complete maintained V16 product, not an isolated ablation.

## Failures and evidence

The 12 zero-reward time-boundary tasks were:

- `adaptive-rejection-sampler`
- `build-cython-ext`
- `configure-git-webserver`
- `extract-moves-from-video`
- `gcode-to-text`
- `gpt2-codegolf`
- `make-doom-for-mips`
- `path-tracing`
- `qemu-startup`
- `raman-fitting`
- `train-fasttext`
- `write-compressor`

The remaining 16 failures reached a normal verifier result with reward zero.
They are valid capability outcomes rather than network, container-start, or
exit-137 failures.

The final `train-fasttext` trace exposed a scheduler classification edge case:
Harbor can raise `RuntimeError: Command timed out after 1800 seconds` from its
outer installed-Agent command instead of `AgentTimeoutError`. The scheduler
now recognizes this only when the traceback proves it occurred in
`_run_agent_phase` through `exec_as_agent` and the trajectory is attributable
to a known Agent version. Runner-setup command timeouts remain infrastructure
errors.

## Verification

- Root suite: 493 passed, two Windows symlink tests skipped.
- V16 fix provider/Agent archive regression slice: 50 passed.
- Ruff check and format check: all 337 maintained `src` and `tests` Python
  files passed.
- Scheduler timeout-classification tests: two passed.
- Changed scheduler and heartbeat proxy passed Ruff check and format check.
- Final audit: 89/89 used `v16-explicit-maintenance-fix4`; 61 pass, 28 zero,
  and no final infrastructure failure.

The large raw state and event logs remain under the ignored local `runs/`
directory. They are retained locally for trajectory forensics but are not
committed as source artifacts.
