# Coding Kid Version 15 — Benchmark-Driven Hardening

This teaching checkpoint packages the cross-cutting reliability fixes exposed
by a complete Terminal-Bench 2.1 evaluation. It is a maintenance release over
Version 14, not a new headline Agent capability.

## Demonstrated Capability

- Search and file reads are bounded by files, bytes, matches, and binary-content
  checks before they can exhaust a minimal task container or enter model
  context.
- Tool schemas reflect workflow mode, repository state, credentials, and live
  manager state, so the model is not offered actions that cannot work.
- Core command guidance is short and direct enough for the model to gather
  terminal evidence instead of avoiding execution.
- Guarded writes, commands, and rollback work in directories without Git by
  using a bounded filesystem checkpoint fallback.
- OpenAI-compatible Responses endpoints can use a custom base URL, max
  reasoning effort, extended request timeouts, and compatibility settings for
  output-limit handling.
- The tracked Terminal-Bench runner persists transitions, resumes without
  repeating valid trials, separates infrastructure retries from ability
  outcomes, and keeps long Cloudflare streaming or non-streaming responses
  alive.

Version 15 does not add a new workflow, task-specific benchmark solutions, or
a claim that k=1 is directly equivalent to k=5 or pass@k leaderboard results.
Credentials, raw runs, datasets, container images, caches, virtual environments,
and generated Cloudflare state are not part of this checkpoint.

## Verification

- Root implementation: 449 tests collected, 448 passed, and one Windows
  symlink test skipped; Ruff lint and format checks passed over 305 Python
  files.
- Root wheel: 278 entries with frozen V1-V14 runtimes plus living V15. A clean
  Python 3.11 install launched every version from an unrelated project.
- Standalone archive: 384 tests collected, 383 passed, and one Windows symlink
  test skipped; Ruff lint and format checks passed over 60 Python files.
- Standalone wheel: 34 entries, with no tests, evaluation files, cache, or
  bytecode; a clean Python 3.11 install launched V15 from an unrelated project.
- No new model request or paid benchmark run was used while packaging V15.

## Evaluation Result

The authorized Terminal-Bench 2.1 run used Coding Kid V15 with
`gpt-5.6-luna`, max reasoning effort, and one valid trial for each of the 89
official tasks:

- 50 passed
- 9 Agent timeouts
- 30 other verifier-zero results
- 0 exit-137 results
- 0 final infrastructure failures
- **50/89 = 56.18% at k=1**

The earlier complete run scored 45/89 (50.56%), with 22 Agent timeouts and 13
exit-137 failures. The root report
`docs/reports/terminal-bench-2.1-k1.md` records the exact protocol, failure
classification, fixes, and limitations.

## Setup and Run

Requirements are Python 3.11+, uv, Docker plus a pre-pulled image for restricted
sandbox modes, and provider credentials for live model use.

```powershell
uv sync --extra dev
uv run coding-kid --sandbox danger-full-access --approval full-access
uv run coding-kid --sandbox workspace-write --sandbox-network
```

The standalone archive runs Version 15 directly. It does not include or depend
on the root project's historical-version launcher.

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
uv build --wheel
```

The deterministic suite uses fake providers and transports. These checks do not
invoke a paid model or start a benchmark batch.

## Evaluation Operations

Tracked, secret-free adapters and Cloudflare scheduler sources are retained
under `evals/terminal-bench-2-1/`. Their README files describe deployment and
resume behavior. Running them is a separate paid benchmark operation and
requires explicit authorization.

## Git Checkpoint

Annotated tag: `version-15-benchmark-driven-hardening`.
