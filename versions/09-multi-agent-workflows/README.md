# Coding Kid Version 09 — Multi-Agent Workflows

This teaching checkpoint adds a bounded, process-local multi-Agent control
plane to Version 08 without replacing the synchronous root Agent loop. The root
can start independent child Agents concurrently, inspect or wait for results,
continue an existing child, request cancellation, and synthesize evidence.

## Demonstrated Capability

- One application-owned `AgentManager` atomically limits active children to
  four and retains up to 16 records with truthful lifecycle states.
- Strict `spawn_agent` and unified `agent` tools provide asynchronous start,
  list, poll, cancellable wait, context-preserving followup, and bounded stop.
- Every child owns its conversation, compaction, todo state, work-tool budget,
  cancellation token, progress, result, and error state.
- Children share cwd, project instructions, Skills, MCP, and user permissions,
  but receive neither the root transcript nor long-term memory.
- Child registries exclude nested Agents, the background-task tool, and
  background `execute`; foreground cancellation terminates the process tree and
  retains partial provider-safe evidence.
- CLI and TUI commands expose `/agents` and `/agent stop <id>`, running counts,
  and lifecycle notifications without waking the model.
- Root interruption or rollback does not revoke already-started child work;
  child IDs remain process-local and explicitly expire after restart.

Version 09 does not provide nested/remote Agents, peer communication, arbitrary
Agent graphs, model overrides, parent-history forks, durable child transcripts,
worktrees, sandboxing, approvals, or overlapping-write merging.

## Verification

- Root implementation: **273 deterministic tests** plus Ruff lint and format
  checks.
- Standalone archive: **231 deterministic tests** plus Ruff lint and format
  checks.
- Ten rounds of four concurrent workers passed without excess concurrency,
  duplicate terminal events, todo leakage, deadlock, or surviving worker
  threads.
- The final wheel contains 121 files, frozen V01–V08 and living V09, with no
  tests, evals, research, `showcase/`, logs, or caches. Frozen V08 matches its
  archive across 20 runtime files, and a clean installation launches V1–V9 plus
  default V09 from an unrelated cwd.
- Three real `openai/gpt-5.6-luna` workflows passed: overlapping research,
  same-Agent implementation/followup with an independently confirmed 10-test
  result, and foreground cancellation with partial evidence, process cleanup,
  and safe persistent-session resume.
- All 51 paid requests, including one retained non-passing short-delay attempt,
  used 117,376 input tokens, 5,411 output tokens, and USD 0.011379095.
- No SWE-bench or paid batch evaluation was run.

## Setup

Requirements:

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` for live use

```powershell
uv sync --extra dev
```

## Run

Start the standalone Version 09 Agent inside the project it should operate on:

```powershell
uv run coding-kid
```

Session selection supports `--new`, `--continue`, `--resume`,
`--list-sessions`, and `--delete-session`. Use `/agents` to inspect child work
and `/agent stop <id>` to request cancellation without a model call.

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

The deterministic tests use fake providers and local processes; they do not
call OpenRouter.

## Git Checkpoint

Annotated tag: `version-09-multi-agent-workflows`.
