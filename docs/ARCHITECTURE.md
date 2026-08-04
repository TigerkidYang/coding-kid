# Architecture

## Overview

Version 07 adds a session-scoped capability runtime without changing the
synchronous model/tool loop introduced by earlier versions. Skills provide
lazy instructions, MCP provides structured tools, and Plugins package and
namespace both.

```text
launcher.py
  |-- v1-v6 -> isolated bundled runtime process
  `-- v7/default -> cli.py
                     |-- SessionStore / MemoryManager
                     |-- CapabilityRuntime
                     |     |-- Skill + Plugin metadata snapshot
                     |     `-- MCP asyncio thread -> stdio / Streamable HTTP
                     |-- non-TTY -> plain chat
                     `-- TTY -> tui.py -> worker -> agent.py -> provider
                                  ^             |       |
                                  `-- events.py <-+       +-> session ToolRegistry
```

The UI remains a projection of canonical state. A successful turn is first
committed by the agent and then appended as one durable session transition.
Failed and interrupted turns roll back the conversation and todos; their audit
records are not replayed into model context.

## Pluggable Capability Runtime

`capability_config.py` strictly reads only the user-owned
`%CODING_KID_HOME%/capabilities.json`. Repository MCP declarations are inert.
`plugins.py` resolves explicitly enabled local manifests and rejects any
declared path whose resolved target leaves the Plugin root. `skills.py`
discovers user, hierarchical project, and Plugin Skills; stores only validated
metadata in the session snapshot; and reads a complete body only on invocation.

`capabilities.py` owns one immutable discovery snapshot and one dedicated
asyncio event-loop thread. Server startup is concurrent. A required failure
aborts startup, while an optional failure becomes a redacted warning. The same
thread retains official MCP SDK clients and stdio subprocesses, bridges tool
calls back to the synchronous agent, cancels timed-out or interrupted calls,
and closes every connection on process exit.

MCP names are normalized and namespaced before they enter `ToolRegistry`.
Collisions are rejected in full. Only JSON-object input schemas are exposed;
descriptions, total count, definition tokens, and results are bounded. MCP
schemas use `strict: false`; built-in and Skill schemas remain strict. The
registry is fixed for a turn and is shared by normal requests, context
estimation, and compaction.

Skill metadata consumes at most 2% of a known context window (or 8,000
characters in passive mode). Explicit `$skill` bodies follow recalled memory in
request-only context and never enter canonical history. A model `skill(name)`
call returns the full body inside the current tool protocol round. At most eight
different Skills load per turn, and Skill loads do not consume the 64-call work
budget.

## Version Launcher and Session Selection

`launcher.py` accepts `v1` through `v7`; V07 is the living default. V1–V6 run
from frozen runtime packages in isolated child processes. Session flags apply
only to V06:

- No flag or `--new` creates a new session.
- `--continue` resumes the most recently updated project session.
- `--resume ID` accepts a complete ID or unique prefix.
- `--list-sessions` lists project sessions without starting the provider.
- `--delete-session ID` soft-deletes the index entry while retaining evidence.

Session selection is scoped by the canonical Git common directory, allowing
worktrees of one repository to share identity. A resolved project root is the
fallback outside Git.

## Durable Session Storage

`sessions.py` owns session identity, persistence, replay, and writer leases.
`CODING_KID_HOME` overrides the default `~/.coding-kid` root.

```text
~/.coding-kid/
  user-memory.sqlite3
  projects/<name>-<identity-hash>/
    state.sqlite3
    sessions/<session-uuid>.jsonl
```

The append-only JSONL log is authoritative for conversation recovery. Each
record contains a sequence number, previous hash, UTC timestamp, payload, and
SHA-256 hash. The creation record captures the immutable `SessionContext` and
context budget. Successful state records contain only new transcript segments
plus the complete bounded active view, compaction checkpoints, todos, and
context-accounting fields. This avoids duplicating the unbounded transcript
while making replay deterministic.

Provider response objects are normalized into provider-input JSON before they
enter conversation state. Optional null fields are omitted recursively, and
replay applies the same normalization for compatibility with logs written by
the original V06 checkpoint. This keeps reasoning, messages, function calls,
and function outputs valid after SDK objects cross a JSON/process boundary.

SQLite provides queryable session metadata, unique paths, memory tables, and
leases. It is rebuildable from JSONL: startup discovers orphan logs and repairs
stale indexes after expired leases. A truncated final line is discarded during
explicit retry; corruption inside the hash chain marks the session damaged.
One renewable lease prevents concurrent writers. A completed turn whose append
fails remains in memory, marks the handle dirty, and blocks further work until
`/session save` succeeds or the process exits.

Resumption restores the original model, cwd, cached project instructions,
transcript, active view, checkpoints, todos, and accounting. The caller must
launch from the original cwd with the original `OPENROUTER_MODEL`.

## Layered Long-Term Memory

`memory.py` implements four explicit layers:

1. Canonical raw evidence in committed session JSONL.
2. Per-session extraction rows with a source sequence cursor and summary.
3. Consolidated typed memories with provenance, status, and usage metadata.
4. A bounded request-only recall projection selected for the current prompt.

Eligible non-current sessions are closed or idle for at least six hours. One
maintenance pass processes at most two sessions. Stage one uses a no-tools model
request to produce validated candidates; stage two consolidates at most 256
candidates and atomically promotes a validated memory set. Cursors advance only
after valid extraction. A project-wide lease prevents duplicate maintenance.
Failures preserve the previous durable memory set and remain retryable.

Automatic extraction writes only project-scoped memories. `/remember --global`
is the sole path to the shared user-memory database. Entries use the Claude
Code-inspired `user`, `feedback`, `project`, and `reference` types. Obvious
credentials are redacted before extraction; raw session logs remain lossless.

Recall uses deterministic lexical ranking rather than embeddings. At most five
active memories and 25 KiB/200 lines enter the request before active history.
They are labeled as untrusted, potentially stale evidence and never enter the
transcript or compaction input. A valid machine-only citation footer is removed
from visible and committed assistant text; only cited, retrieved IDs receive a
usage update.

`CODING_KID_MEMORY_MODE` accepts `auto`, `manual`, or `off`. Automatic mode is
the default and runs one visible, bounded startup maintenance worker. Manual
mode preserves recall and explicit commands without automatic model requests.

## Request and Commit Flow

1. The CLI or TUI selects and acquires one durable session.
2. The current user text retrieves a bounded, request-only memory attachment
   and deterministically loads explicitly mentioned Skills.
3. The real user message enters the in-memory transcript and active context.
4. The agent assembles cached project context, Skill metadata, recalled memory,
   explicit Skill bodies, active history, todos, and recovery guidance for each
   provider step using one tool-registry snapshot.
5. Compaction may replace only the active view; recalled memory is not included
   in the compaction source. A checkpoint is committed only when its estimated
   request is smaller than the original. The summary prompt includes
   deterministic tool-count evidence, and a summary that denies recorded tool
   activity is rejected atomically.
6. A valid final response is stripped of a valid memory-citation footer,
   committed to canonical conversation state, and emitted to the UI.
7. Cited memory usage is updated best-effort. The complete session transition
   is then hash-chained and flushed before SQLite metadata advances.

## Other Modules

- `tui.py` owns the full-screen transcript, composer, activity state, session
  and memory commands, and visible persistence/memory failures. Assistant
  Markdown cells are constructed with their initial source so terminal-only
  responses remain visible even when no text-delta event preceded completion.
- `events.py` defines typed agent lifecycle events and cooperative cancellation.
- `context.py` captures runtime facts and layered project `AGENTS.md` files.
- `context_manager.py` separates canonical transcript from bounded active
  context and accounts for the model window.
- `compaction.py` creates atomic structured handoffs for older active history.
- `agent.py` owns the bounded model/tool loop and request-only context injection.
- `capability_config.py`, `plugins.py`, `skills.py`, and `capabilities.py` own
  user configuration, local packages, lazy instructions, and MCP lifecycle.
- `provider.py` implements complete and streaming OpenRouter Responses calls.
- `parser.py` extracts text, tool calls, and valid memory citations.
- `tools.py` contains built-in tools and the session-level registry abstraction.

## Security and Scope Boundaries

Storage directories and files receive restrictive permissions where the host
supports them. Raw logs may contain prompts and tool results, so users must
treat `CODING_KID_HOME` as sensitive and use soft deletion deliberately.

Version 07 does not add encryption at rest, remote synchronization, vector
search, a generic background-task framework, multi-agent workflows, sandboxing,
approvals, a Plugin marketplace, OAuth, or non-tool MCP primitives. All tools
still run with the current user's permissions.
