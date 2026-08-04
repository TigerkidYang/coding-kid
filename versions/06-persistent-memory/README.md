# Coding Kid Version 06 — Persistent Sessions and Long-Term Memory

This teaching checkpoint adds deterministic multi-session persistence and
layered long-term memory to Version 05's streaming coding agent.

## Demonstrated Capability

- Creates independent project sessions and lists, resumes, continues, or
  soft-deletes them across process restarts.
- Stores a hash-chained append-only JSONL history plus rebuildable SQLite
  metadata and prevents concurrent writers with renewable leases.
- Restores transcript, bounded active context, compaction checkpoints, todos,
  model configuration, cached project instructions, and context accounting.
- Recovers partial writes and orphaned indexes, refuses internal hash-chain
  corruption, and safely retries a turn flushed before its index update.
- Extracts structured candidate memory from eligible prior sessions, then
  atomically consolidates typed, provenance-linked durable memories.
- Automatically creates only project memory; cross-project user memory requires
  an explicit `/remember --global ...` command.
- Retrieves at most five relevant memories into request-only context and tracks
  actual use through hidden, validated memory citations.
- Exposes session and memory state through both the plain terminal and Textual
  TUI without changing the existing model/tool loop or rollback semantics.

The living repository passed all 171 deterministic tests, Ruff lint and format
checks, wheel inspection, fresh-install V1–V6 launches, and installed V06
session listing/resumption. Verification made no live provider request and ran
no paid benchmark or SWE-bench job.

## Setup

Requirements:

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` for live use

```powershell
uv sync --extra dev
```

`CODING_KID_HOME` overrides the default `~/.coding-kid` data directory.
`CODING_KID_MEMORY_MODE=auto|manual|off` controls memory maintenance and recall.
Automatic mode is the default and may make additional model requests when
eligible prior sessions exist.

## Run

Start a new session inside the project it should operate on:

```powershell
uv run coding-kid
```

This standalone archive starts V06 directly and provides `--continue`,
`--resume`, `--list-sessions`, and `--delete-session` without carrying the root
cross-version launcher. Inside a session, use `/session`, `/sessions`,
`/session save`, `/memory`,
`/memory search`, `/memory sync`, `/remember`, and `/forget`.

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

The archived suite covers deterministic persistence and memory behavior with
fake providers. It does not spend API credits.

## Data and Intentional Limits

Raw JSONL logs are intentionally lossless and may contain prompts, code, and
tool results. Files receive restrictive permissions where supported, and
obvious credentials are redacted before derived-memory generation, but Version
06 does not provide encryption at rest.

Version 06 has no vector database, remote memory synchronization, generic
background-task framework, multi-agent work, MCP, skills, plugins, sandbox, or
approval flow. Tools still run with the current user's permissions.

The cross-version launcher remains an unnumbered root-project facility. This
archive does not recursively carry the V1–V5 bundled runtimes.

## Git Checkpoint

Matching annotated tag: `version-06-persistent-memory`.
