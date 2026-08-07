# Tasks

## Current Core Version: 15 — Benchmark-Driven Hardening

Completion status: complete. The user requested version completion on
2026-08-07. The standalone checkpoint is archived under
`versions/15-benchmark-driven-hardening/` with annotated tag
`version-15-benchmark-driven-hardening`.

### Goal

Turn the maintenance work exposed by Terminal-Bench 2.1 into one coherent
reliability release. Version 15 does not add a new headline capability; it
hardens the existing coding loop, tool surface, checkpoint behavior, provider
compatibility, and evaluation operations against realistic minimal Linux tasks
and long-running remote inference.

### Included Scope

- Bounded, binary-aware file inspection and safer POSIX command execution in
  resource-constrained task containers.
- Mode-, state-, credential-, and repository-aware tool exposure, plus shorter
  core command guidance that encourages direct evidence gathering.
- Bounded filesystem checkpoint fallback when Git is absent or the working
  directory is not a repository.
- OpenAI-compatible Responses API support for configurable base URLs, max
  reasoning effort, slow endpoints, and endpoints that reject output limits.
- Resumable Terminal-Bench 2.1 adapters and Cloudflare scheduling that preserve
  valid results, distinguish infrastructure retries from ability failures, and
  keep long non-streaming JSON responses alive.
- Frozen V14 runtime plus installed V1-V15 selection with V15 as the default.
- A reproducible Terminal-Bench 2.1 k=1 report for Coding Kid V15 with
  `gpt-5.6-luna` at max reasoning effort.

### Excluded Scope

- A new user-facing Agent capability, new workflow mode, or new research topic.
- Changes designed to solve individual benchmark tasks or task-specific prompt
  special cases.
- Claims of leaderboard equivalence between this k=1 run and k=5 or pass@k
  results.
- Bundling benchmark run logs, credentials, caches, datasets, container images,
  or generated Cloudflare state in the teaching archive or wheel.
- Another paid benchmark run during version packaging.

### Completion Criteria

- Broad inspection cannot trigger unbounded memory use; the final benchmark has
  no exit-137 result.
- Non-Git task directories retain guarded write/execute/checkpoint behavior.
- The model sees only usable tools for the current runtime state and can use
  terminal/file tools without contradictory command guidance.
- Terminal-Bench scheduling survives restart and transport faults without
  converting infrastructure errors into ability zeros or repeating valid work.
- All 89 official Terminal-Bench 2.1 tasks have one valid k=1 result, with the
  protocol and limitations recorded honestly.
- The root regression suite and Ruff pass; the wheel contains V1-V15; every
  installed teaching version launches from an unrelated project.
- The standalone V15 archive passes its own regression and packaging checks.

### Implementation Sequence

1. Harden resource-bounded tools, runtime-aware schemas, command guidance, and
   checkpoint fallback based on the first complete benchmark run.
2. Build and stabilize resumable local/Cloudflare Terminal-Bench operations,
   including durable state and long-response keepalives.
3. Run one fresh authorized 89-task k=1 evaluation and supplement only trials
   that lacked a valid infrastructure-independent result.
4. Freeze V14, advance the installed launcher to V15, update durable records,
   and independently verify the V15 teaching archive.

### Benchmark Result

- Terminal-Bench 2.1: 89/89 valid tasks, 50 passed, 9 Agent timeouts, and 30
  other verifier-zero results.
- Score: **50/89 = 56.18%** at k=1.
- Infrastructure failures in the final result: 0; exit-137 results: 0.
- The earlier complete run scored 45/89 (50.56%), with 22 Agent timeouts and 13
  exit-137 failures.

See `docs/reports/terminal-bench-2.1-k1.md` for protocol, failure
classification, fixes, and limitations.

### Verification Result

- Root project: 449 tests collected, 448 passed, and one Windows symlink test
  skipped; Ruff lint and format checks passed over 305 Python files.
- Root wheel: 278 entries, including frozen V1-V14 runtimes plus living V15,
  with no tests, evaluation files, caches, or bytecode.
- A clean Python 3.11 installation launched V1-V15 from an unrelated project;
  V15 remained the latest default.
- Standalone archive: 384 tests collected, 383 passed, and one Windows symlink
  test skipped; Ruff lint and format checks passed over 60 Python files.
- Standalone wheel: 34 entries with the archive-only entry point and no tests,
  evaluation files, caches, or bytecode; a clean Python 3.11 install launched
  V15 from an unrelated project.
- No new model request or paid benchmark run was used for version packaging.
