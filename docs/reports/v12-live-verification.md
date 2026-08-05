# Version 12 Live Verification

Date: 2026-08-05

## Artifact and Environment

- Artifact: `output/v12-verification/coding_kid-0.1.0-py3-none-any.whl`
- Clean runtime: isolated Python 3.11 virtual environment
- Model: `openai/gpt-5.6-luna`
- Interface: installed Version 12 Textual TUI driven through a Windows
  pseudo-terminal
- Restricted backend: Docker Desktop with
  `python:3.11-slim-bookworm`

No SWE-bench run or paid batch evaluation was authorized or performed.

## Deterministic and Packaging Results

- Pytest collected 384 tests: 383 passed and one Windows symlink test was
  skipped. Runtime: 108.5 seconds.
- Ruff lint and formatting checks passed over all maintained source and tests.
- Ten repeated stress rounds passed approval cancellation, serialized
  10-worker effects, external-edit rollback conflicts, child approval routing,
  background descendant cleanup, and ordered parallel reads.
- The wheel contains 193 entries / 189 Python files, including all 23 frozen
  V11 runtime files. It contains no tests, evaluations, research, `showcase/`,
  caches, bytecode, or logs.
- A clean installation launched explicit V1-V12 from an unrelated Git
  directory. Each version used isolated application state and exited before a
  provider request.

## Real Terminal Scenarios

### Plan, Cautious approval, Review, and Accept

The installed TUI in `plan + cautious + danger-full-access` asked one structured
question, submitted a plan, and transitioned through the application-owned
approval gate. A one-shot write approval created `result.txt` containing exactly
`V12谨慎-ok`. A second same-path write was denied with feedback and did not
replace the content. The persisted session entered Review, displayed its
checkpoint and created-file summary, and accepted the stage.

The pseudo-terminal driver initially combined a short answer and Enter too
tightly; Textual displayed the answer without submitting it. Splitting text and
Enter fixed the driver. This caused no project side effect.

### Auto and conflict-safe rollback

Under `implementation + auto + danger-full-access`, two ordinary writes ran
without a prompt. The checkpoint reported one modified and one created file.
Real rollback removed the new file and restored the tracked file to its exact
pre-stage dirty content, `preexisting user dirty change`, rather than its Git
commit.

### Independent control axes

Under `implementation + full-access + read-only`, no approval dialog appeared,
but the built-in write returned `Sandbox blocked write: sandbox is read-only`.
The model completed with `READ_ONLY_VERIFIED`, no file was created, and no
container remained. The cautious/danger-full-access scenarios still prompted,
showing that approval remains active without sandbox restriction. Plan and
Review mutation bypasses are covered by the runtime tests.

### Interrupt, child Agent, and background work

Pressing Escape while a write approval was pending produced matching approval-
cancelled and turn-interrupted events. No `ToolStarted` side effect occurred and
the target was absent.

A root-approved child Agent then requested a write. The request appeared in the
root TUI through the shared broker and was denied; `child.txt` was absent. A
separate workspace-write run approved one `sleep 60` background task. Exiting
the application reclaimed the task and its Docker container; the final labeled
container count was zero.

### Persistent checkpoint and non-persistent grant

A cautious session granted the same-path write for its current process and
created `resume.txt`. On resume, the checkpoint and `Created: 1` state returned,
but the process grant did not: the same write requested approval again and was
denied. The original `first-session` content remained.

This trial exposed a real replay defect: terminal `turn_failed`,
`turn_interrupted`, and `turn_steered` records contained complete retained tool
rounds and workflow state but were not replayed. Replay now restores those
records only when they contain a complete model/tool round; failures before any
complete round remain audit-only. Deterministic tests cover all three terminal
kinds and the earlier audit-only behavior.

## Usage Bound

The durable root transcripts contain 11 completed model rounds. Including the
short transient driver attempt, interrupted request, child request, and
non-durable terminal rounds, the live work used no more than 18 model responses.
Exact provider cost is not persisted. Given the short bounded inputs and
outputs, total task spend is conservatively below USD 0.10, within the USD 1.00
allowance.

## Outcome

All Version 12 completion criteria passed after the replay correction. No paid
benchmark or batch evaluation was run.
