# Version 10 Live Verification

Date: 2026-08-05

## Artifact and Environment

- Artifact: `dist/coding_kid-0.1.0-py3-none-any.whl`
- Clean runtime: Python 3.13.11 in a temporary virtual environment
- Model: `openai/gpt-5.6-luna`
- Interface: the installed Version 10 full-screen Textual TUI
- Persistent session: one isolated temporary `CODING_KID_HOME`

No SWE-bench run or paid batch evaluation was authorized or performed.

## Deterministic and Packaging Results

- Pytest: 289 passed in 97.55 seconds.
- Ruff lint and format checks: passed.
- Stress: 10/10 rounds passed, with five probes per round covering safe-call
  overlap, exclusive barriers, FIFO TUI steering, hard interruption, and
  foreground process-tree cancellation.
- Wheel: 143 entries, including 139 Python files and nine frozen CLI runtimes
  for V01–V09. It contains no tests, evaluations, `showcase/`, logs, caches, or
  bytecode.
- Clean install: explicit V1–V10 and default V10 all launched and exited from an
  unrelated directory without a provider request.

## Real TUI Scenarios

### Soft steering and foreground cancellation

The model started a foreground command that printed `READY_V10`, waited 120
seconds, and would then have created a delayed sentinel. A new TUI submission
was accepted while the turn was active. The UI showed one queued steering item,
applied it at the control boundary, cancelled the process tree, and retained a
bounded tool result containing the ready marker and cancellation status. The
delayed file was never created and no worker survived.

### Hard interrupt and completed-effect retention

The model first completed a write of `HARD_EVIDENCE_V10`, then entered another
120-second foreground command. Escape performed a hard interrupt rather than a
soft steer. The completed write call and matching output remained in the
protocol transcript, the running process was cancelled with partial evidence,
and its delayed sentinel was absent. Resuming the same persistent session
preserved both complete rounds.

The first no-tool recall request revealed that retained protocol evidence alone
did not reliably ground the model: it incorrectly said the value was not
available. The system context was then corrected to identify completed
historical tool arguments and matched outputs as authoritative evidence, and a
deterministic regression test was added. A rebuilt, clean-installed wheel
resumed the same session in the real TUI and replied exactly
`HARD_EVIDENCE_V10` without calling a tool.

### FIFO steering

During another foreground wait, `FIFO_ONE` was submitted first and consumed at
the next boundary. While its continuation was active, `FIFO_TWO` was submitted.
The TUI displayed and processed the inputs in order, ending with the requested
exact answer `ONE THEN TWO`. Neither submission was silently discarded.

## Usage Bound

The persistent session contains eight unique paid provider responses. Its
committed snapshots contain 17,070 last-step input tokens in aggregate; this is
a diagnostic sum across snapshots, not a billable-token total. Coding Kid does
not persist exact provider cost, so no false precision is claimed. Based on the
known model rate and the short bounded outputs, total live spend for this task
is conservatively below USD 0.02, well inside the standing USD 1.00 allowance.

## Outcome

All Version 10 completion criteria passed. The implementation is ready for the
user's stage-completion confirmation; archive creation, annotated tagging, and
push remain intentionally deferred until that confirmation.
