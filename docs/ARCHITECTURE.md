# Architecture

## Overview

Version 10 makes the synchronous root model/tool loop controllable without
turning it into a workflow engine. `TurnController` owns active-step
cancellation and a bounded FIFO steer queue; `run_turn` owns explicit step,
recovery, budget, stall, and terminal transitions. Existing application-owned
Agent, background-task, capability, session, and memory managers remain intact.

```text
launcher.py
  |-- v1-v9 -> isolated bundled runtime process
  `-- v10/default -> cli.py
                     |-- SessionStore / MemoryManager
                     |-- AgentManager -> child run_turn workers
                     |-- BackgroundTaskManager -> shell process trees
                     |-- CapabilityRuntime
                     |     |-- Skill + Plugin metadata snapshot
                     |     `-- MCP asyncio thread -> stdio / Streamable HTTP
                     |-- non-TTY -> plain chat
                     `-- TTY -> tui.py -> worker -> agent.py -> provider
                                  ^             |       |
                                  `-- events.py <-+       +-> session ToolRegistry
```

The UI remains a projection of canonical state. Complete model/tool rounds are
the evidence boundary. Failed, steered, and interrupted turns retain completed
rounds and todo effects, discard incomplete assistant streams, and write a
reasoned durable transition. Temporary compaction projections are rolled back
on failure while newly completed transcript rounds are preserved. Already
started child Agents and background tasks remain discoverable.

## Controllable Turn Runtime

`turn_control.py` defines the public phases, transition reasons, resource
limits, pending-input records, and cancellation ownership. The TUI accepts up
to eight active-turn inputs, cancels the current step with reason `steered`,
commits its retained evidence, and consumes queued inputs FIFO using a fresh
token. `Esc` uses the distinct `interrupted` reason and does not continue.

The agent caps one turn at 80 steps, 64 work-tool calls, six recoveries, four
identical actions, and 30 minutes. Provider transport retries are explicit,
cancellation-aware, observable, and limited to three attempts. Output-limit
responses can recover twice. Repeated identical name/arguments/result triples
emit a stall event on the third occurrence and disable tools on the fourth so
the model must synthesize from existing evidence.

Only tools carrying explicit `parallel_safe` metadata may overlap. The living
registry marks built-in `read` and `search`; all file mutations, terminal work,
task/Agent controls, Skills, MCP tools, and unknown future tools default to
exclusive. Consecutive safe calls run in batches of at most four workers.
Exclusive calls form barriers, and function-call outputs are committed in the
model's original order regardless of completion order.

## Multi-Agent Control Plane

`agents.py` owns random `agent_<12 hex>` identities, records, worker threads,
events, cancellation, retention, and shutdown. At most four records can be in
`starting`, `running`, or `stopping`; at most 16 remain addressable, and only
the oldest terminal record is evicted. A child task is capped at 12,000 prompt
characters, 32 model/tool steps, 32 work-tool calls, and a 50,000-character
final result. `wait` is cancellation-aware and capped at 30 seconds.

`spawn_agent` reserves a slot atomically and returns immediately. The unified
`agent` tool lists, polls, waits, follows up, or requests stop. Stop is
cooperative: it first exposes `stopping` and reports `stopped` only after the
worker exits. `followup` retains the selected child's canonical context but can
only start from a terminal state. Terminal events are emitted once; they update
CLI/TUI state but never initiate a provider request.

Each child begins with only its self-contained delegated prompt. It shares the
immutable `SessionContext`, cwd, model, project instructions, Skills catalog,
and application-owned MCP runtime, but it does not receive the root transcript
or long-term memory. Its registry contains foreground terminal/file tools, its
own todo tool, Skills, and MCP. It excludes `spawn_agent`, `agent`, `task`, and
the background form of `execute`. Foreground cancellation terminates the shell
process tree and retains partial command evidence in the child transcript.

`TodoState` is explicit on all formal paths. The root instance is persisted and
rolled back with root turns; every child owns another instance. Compatibility
wrappers retain a default state for historical direct callers only. MCP event
collection is locked because multiple child threads may load Skills or invoke
MCP concurrently; the MCP clients remain owned by their one asyncio thread.

## Background Task Runtime

`background_tasks.py` owns task identity, process state, output readers,
completion watchers, bounded event delivery, and shutdown. `execute` retains
its existing foreground behavior unless the model explicitly passes
`background=true`; background commands inherit cwd and the Unicode-safe shell
environment, close stdin, and return immediately without a PTY.

Each task has one monotonic transition from `running` to `completed`, `failed`,
or `stopped`. IDs are random `task_<12 hex>` values. At most eight processes
run concurrently and 32 records remain addressable; only the oldest terminal
record can be evicted. Stdout and stderr each retain a 256,000-byte tail with an
omission marker. UI events, command summaries, and the dynamic model projection
are separately bounded.

Two byte-reader threads and one watcher drain every process without blocking
the Agent loop. On Windows, the shell starts suspended, enters a kill-on-close
Job Object, and only then resumes; termination combines `taskkill /T` with the
Job boundary. This closes both descendant-creation races. `stop` is idempotent,
`wait` is cancellable and capped at 30 seconds, and concurrent `stop`/`close`
operations share a termination lock and close-completion barrier. Application
shutdown stops all running trees and joins task threads before closing MCP and
persistent session resources.

The manager is created afresh on each Coding Kid process start. Task IDs and OS
processes never enter session logs, compaction, or memory. Successful tool-call
protocol rounds still persist normally; after resume, an old ID yields an
explicit unknown/expired error. Task completion produces UI events only and
never wakes the model or initiates a provider call.

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

## Foreground Terminal Boundary

`terminal.py` owns the complete built-in `execute` process boundary. On
Windows, model commands enter PowerShell through its UTF-16LE `EncodedCommand`
protocol; the script explicitly selects UTF-8 output, and Python child
processes receive UTF-8 environment hints. Standard input is closed so a
foreground command cannot silently wait for interactive input.

Stdout and stderr remain byte streams while two readers drain them. Each stream
keeps a bounded head and tail, so a noisy process cannot allocate unbounded
memory before the registry's existing 50,000-character result limit applies.
UTF-8 is preferred at decode time, then the platform legacy codec, then lossy
UTF-8. PowerShell's redirected CLIXML progress envelope is discarded while
real error records are retained.

Timeout returns conventional exit code 124, partial output, elapsed time, and a
`timed_out` marker. Timeout, interruption, and unexpected parent failure
terminate the process tree; pipe draining has its own deadline for inherited
handles. CLI output is configured for UTF-8 and has a codec-safe fallback, so
displaying a command or answer cannot invalidate the Agent protocol round.

## Version Launcher and Session Selection

`launcher.py` accepts `v1` through `v10`; V10 is the living default. V1–V9 run
from frozen runtime packages in isolated child processes. Living-runtime
session flags select V10 sessions:

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

1. The CLI or TUI selects a durable session and creates one process-local task
   manager.
2. The current user text retrieves a bounded, request-only memory attachment
   and deterministically loads explicitly mentioned Skills.
3. The real user message enters the in-memory transcript and active context.
4. The agent assembles cached project context, Skill metadata, recalled memory,
   explicit Skill bodies, active history, todos, the current bounded task
   summary, and recovery guidance for each provider step using one tool-registry
   snapshot.
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
- `background_tasks.py` owns process-local task state, output, events, and
  cleanup.
- `capability_config.py`, `plugins.py`, `skills.py`, and `capabilities.py` own
  user configuration, local packages, lazy instructions, and MCP lifecycle.
- `provider.py` implements complete and streaming OpenRouter Responses calls.
- `parser.py` extracts text, tool calls, and valid memory citations.
- `tools.py` contains built-in tools and the session-level registry abstraction.

## Security and Scope Boundaries

Storage directories and files receive restrictive permissions where the host
supports them. Raw logs may contain prompts and tool results, so users must
treat `CODING_KID_HOME` as sensitive and use soft deletion deliberately.

Version 10 does not add encryption at rest, remote synchronization, vector
search, persistent or remote jobs, nested/remote Agent graphs, sandboxing,
approvals, a workflow DSL, a Plugin marketplace, OAuth, or non-tool MCP
primitives. All tools still run with the current user's permissions.
