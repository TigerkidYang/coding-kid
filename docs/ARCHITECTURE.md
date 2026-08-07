# Architecture

## Overview

Version 15 is a benchmark-driven maintenance layer over Version 14. It keeps the
same collaboration, Web, execution, workflow, and UI architecture while
hardening resource-bounded inspection, runtime-aware tool exposure, non-Git
checkpoints, OpenAI-compatible provider behavior, and reproducible evaluation
operations. Version 14 remains frozen as the pre-maintenance runtime.

```text
launcher.py
  |-- v1-v14 -> isolated bundled runtime process
  `-- v15/default -> cli.py
                     |-- SessionStore / MemoryManager
                     |-- WorkflowState / PermissionBroker
                     |-- WorkflowRuntime / CheckpointManager
                     |-- SandboxRuntime -> path policy / Docker boundary
                     |-- AgentManager -> scoped child run_turn + session managers
                     |     `-- WorktreeManager -> baseline/diff/reconcile/integrate
                     |-- WebRuntime -> Brave search / pinned public-text GET
                     |-- BackgroundTaskManager -> PTY/pipe execution sessions
                     |-- CapabilityRuntime
                     |     |-- Skill + Plugin metadata snapshot
                     |     `-- MCP asyncio thread -> stdio / Streamable HTTP
                     |-- non-TTY -> plain chat
                     `-- TTY -> tui.py -> worker -> agent.py -> provider
                                  ^             |       |
                                  `-- events.py <-+       +-> session ToolRegistry
```

## Benchmark-Driven Hardening

`tools.py` bounds search by file count, aggregate bytes, per-file bytes, and
match count, and treats binary reads conservatively. `capabilities.py` builds a
tool surface from the current workflow mode, repository state, credentials, and
live manager state so impossible tools are omitted before model selection.

`checkpoints.py` prefers Git snapshots but falls back to bounded filesystem
enumeration when Git is unavailable or the project is not a repository. Both
paths retain the same conflict-aware rollback contract; the fallback does not
turn ignored or outside-project effects into rollback promises.

The evaluation runtime under `evals/terminal-bench-2-1/` is operational tooling,
not part of the installed Agent. Its scheduler persists state atomically,
separates infrastructure retry from verifier outcomes, and resumes without
repeating valid work. The Cloudflare heartbeat proxy preserves long streaming
SSE responses and non-streaming JSON Responses calls without changing the
upstream JSON payload.

The UI remains a projection of canonical state. Complete model/tool rounds are
the evidence boundary. Failed, steered, and interrupted turns retain completed
rounds and todo effects, discard incomplete assistant streams, and write a
reasoned durable transition. Temporary compaction projections are rolled back
on failure while newly completed transcript rounds are preserved. Already
started child Agents and root execution sessions remain discoverable.

## Permission-Governed Workflow

`workflow.py` owns the durable `plan`, `implementation`, and `review` mode plus
the approved plan and checkpoint identity. The registry removes invalid tools
from the model schema, while `PermissionBroker` repeats the mode check before
dispatch so a fabricated hidden-tool call still fails. Plan exposes read,
search, Skill loading, structured questions, and plan submission. Review
exposes read, search, and Skill loading. Both modes receive a filtered `task`
schema for list, poll, and wait only; repeated mode enforcement rejects write,
check, interrupt, or stop even if a fabricated call bypasses that schema.

`permissions.py` classifies every tool as read-only, interaction, project write,
command, destructive, external, or control. Unknown and dynamic tools default
to external. The broker checks mode, hard metadata rules, process-local grants,
approval policy, and finally sandbox preflight. Only then may `ToolStarted` be
emitted. Cautious asks for all sensitive effects, Auto admits normal
write/patch calls, and Full Access suppresses prompts without weakening hard or
sandbox denials. Missing interactive channels deny safely.

`workflow_runtime.py` owns structured Plan interactions and serializes every
sensitive effect across root and child workers. An approved plan creates a
checkpoint before Implementation; direct Implementation creates one before its
first sensitive action. Approval may retain context or replace only the
model-visible projection with the approved implementation instruction while
preserving the canonical transcript.

## Change Checkpoints

`checkpoints.py` enumerates Git-tracked and non-ignored untracked files, stores
content-addressed baseline bytes and types in protected session state, and
records hashes after each sensitive effect. File count and byte limits are hard
boundaries; an unreadable, unsupported, or oversized tree blocks mutation.

Rollback requires execution sessions and child Agents to stop, then compares the
live tree with the last application-recorded tree. Any difference is treated as
a possible external edit and refuses the whole rollback. A safe rollback
restores the exact pre-stage state and removes stage-created non-ignored files.
Ignored output, project-external effects, and remote MCP effects are outside the
promise. Accepting changes removes the protected checkpoint.

## Sandbox Control Plane

`sandbox.py` defines `read-only`, `workspace-write`, and
`danger-full-access`. Restricted startup verifies both the Docker daemon and a
pre-existing image. Any failure aborts startup; no command parser, model output,
or tool error can select a broader policy or trigger an unsandboxed retry.

Built-in file tools resolve absolute targets before use, require containment
under the resolved project root, and therefore reject traversal plus symlink or
junction escape. Writes are denied globally in `read-only`; `workspace-write`
also protects `.git` and `.coding-kid`. The command side mounts the project at
`/workspace`, overlays those metadata paths read-only, uses a read-only
container root plus bounded tmpfs, drops capabilities, enables
`no-new-privileges`, and bounds PIDs, memory, and CPUs. It passes only fixed
Unicode and home variables. Network is `none` unless explicitly enabled, and
the Docker socket is never mounted.

Every restricted execution session receives a random named and labeled
container. Non-interactive sessions attach pipes; interactive sessions attach
the Docker client to a host PTY and use `-it`, creating a real terminal inside
the same continuing container. A readiness `check` uses bounded `docker exec`
and retries only the short startup-registration race. Normal completion relies
on `docker run --rm`; stop, Agent cleanup, and shutdown also force-remove the
container. Isolation, resources, metadata, environment, and network policy stay
fixed for the complete session lifetime.

The provider, durable session/memory stores, project-instruction loader, and
inert Skills remain host-side application control-plane components. Restricted
sessions do not start or advertise MCP tools because neither local MCP
subprocesses nor arbitrary remote effects fit the Docker boundary. The TUI and
plain CLI expose the effective mode, backend, image, root, and network state.
`danger-full-access` deliberately bypasses Docker and retains the historical
host behavior.

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

`spawn_agent` reserves a slot atomically and returns immediately. It defaults to
`worktree` isolation, while `shared` remains explicit compatibility behavior.
The unified `agent` tool lists, polls, waits, follows up, requests stop, reviews
a diff, reconciles, integrates, or explicitly discards. Stop is
cooperative: it first exposes `stopping` and reports `stopped` only after the
worker exits. `followup` retains the selected child's canonical context but can
only start from a terminal state. Terminal events are emitted once; they update
CLI/TUI state but never initiate a provider request.

Each child begins with its delegated prompt and may receive zero to eight recent
root rounds. Forking retains only user messages and visible assistant messages,
is capped at 24,000 characters, and excludes tool calls, tool outputs, and hidden
reasoning. It does not receive long-term memory. Its registry contains cwd-bound
file and execution-session tools, Web research, Skills, and MCP, but excludes
nested Agent controls.
Every child run creates a private session manager: its IDs never appear in the
root list, and completion, failure, or cancellation stops every child-owned
process/container after retaining bounded final evidence.

`worktrees.py` keeps the stable repository root separate from the child's cwd.
It captures tracked changes plus bounded non-ignored untracked files, creates a
private baseline commit with hooks disabled, and then commits only the child
delta. Manifests live in protected session state outside the repository. Every
operation validates the owned path, branch namespace, and baseline ancestry.

`diff` never mutates. `integrate` first verifies the root fingerprint and runs a
whole-patch `git apply --check`; only then does it apply the child delta to the
root and mark it `integrated_pending`. Existing V12 checkpoint preparation runs
before that effect. Stage rollback restores the root and returns the workspace
to `ready`; stage acceptance removes the owned worktree and branch. A changed
root requires `reconcile`, which recreates the dirty baseline and performs the
three-way application only inside the child workspace. Conflicts remain private
and no partial merge enters the root. Discard requires explicit confirmation;
active manifests become orphaned, not deleted, after restart.

## Bounded Web Research

`web.py` owns two GET-only capabilities. `web_search` calls only Brave's fixed
Search endpoint, reads `BRAVE_SEARCH_API_KEY` from the process environment, and
bounds a query to 400 characters / 50 words and results to ten. `web_fetch`
accepts only HTTP(S) on standard ports with no embedded credentials, follows at
most five redirects, accepts public text/HTML only, reads at most 1,000,000
identity-encoded bytes, extracts at most 30,000 text characters, and never
persists a download.

Every fetch destination is resolved before use. All returned addresses must be
globally routable; loopback, private, link-local, reserved, multicast, and mixed
public/private answers fail closed. The HTTP(S) connection is pinned to a
validated address while retaining the original Host header and TLS server name,
and every redirect repeats validation. Response text is explicitly labeled
untrusted and includes its final source URL; search results are numbered for
citation. The system prompt tells the model to treat page text as data rather
than instructions and to cite sourced factual claims.

Both tools are external effects. Plan, Implementation, and Review can expose
them, but Cautious/Auto approval still governs access and fetch grants are
host-scoped. Restricted sandboxes require the immutable startup network flag;
Full Access cannot override a disabled sandbox network. Children inherit the
same Web runtime and policy.

`TodoState` is explicit on all formal paths. The root instance is persisted and
rolled back with root turns; every child owns another instance. Compatibility
wrappers retain a default state for historical direct callers only. MCP event
collection is locked because multiple child threads may load Skills or invoke
MCP concurrently; the MCP clients remain owned by their one asyncio thread.

## Continuous Execution Runtime

`background_tasks.py` owns every root execution identity, whether a command
finishes quickly, explicitly starts in the background, outlives its initial
`yield_time_ms`, or requests an interactive terminal. Registration happens
before waiting, so turn interruption retains a stable session rather than
silently restarting or losing the process. `background=true` is immediate
yield, not a separate implementation.

`terminal.py` supplies two boundaries. Non-interactive commands retain separate
bounded byte pipes and Windows Job/POSIX process-group cleanup. Interactive
commands use pinned pywinpty/ConPTY on Windows and a system PTY on Unix; output
is a combined terminal stream, input can be submitted later, ANSI transport
codes are removed from model-visible text, and Ctrl+C is distinct from stop.
Interactive environments set `PYTHON_BASIC_REPL=1` because Python 3.13's new
REPL corrupts non-BMP input such as emoji through ConPTY; ordinary programs
ignore the variable and Python retains its Unicode-safe basic REPL.

Each stream preserves a bounded head and tail plus an independent recent window
for incremental cursors. All bytes also enter per-session temporary logs until
manager shutdown. Poll, write, and wait consume only unread bytes and mark any
cursor gap. At most eight sessions run and 32 records remain; only the oldest
ended record is evicted. Shutdown stops complete process trees and containers,
joins readers/watchers, and removes temporary logs.

The `task` tool lists, polls, waits, writes, interrupts, stops, or checks a
session. `check` is separate evidence: on the host it runs a bounded command in
the project environment; under Docker it runs inside the live named container.
Neither a running state nor terminal output is automatically called ready.
Write/check are command effects, interrupt/stop are destructive, and
list/poll/wait are read-only. IDs and processes remain process-local; after
restart old IDs report unknown/expired. Completion emits UI events but never
initiates a model call.

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

## Non-Interactive Terminal Compatibility

The original non-interactive path remains inside the unified manager. On
Windows, model commands enter PowerShell through its UTF-16LE `EncodedCommand`
protocol; the script explicitly selects UTF-8 output, and Python child
processes receive UTF-8 environment hints. Standard input stays closed unless
the caller explicitly requests `interactive=true`.

Stdout and stderr remain byte streams while two readers drain them. Each stream
keeps a bounded head and tail, so a noisy process cannot allocate unbounded
memory before the registry's existing 50,000-character result limit applies.
UTF-8 is preferred at decode time, then the platform legacy codec, then lossy
UTF-8. PowerShell's redirected CLIXML progress envelope is discarded while
real error records are retained.

The compatibility `run_command` helper retains its 120-second timeout for
bounded probes and legacy paths. Unified root `execute` instead yields a live
session after the requested wait. CLI output remains UTF-8 with a codec-safe
fallback, so displaying command evidence cannot invalidate a model round.

## Version Launcher and Session Selection

`launcher.py` accepts `v1` through `v13`; V13 is the living default. V1–V12 run
from frozen runtime packages in isolated child processes. Living-runtime
session flags select V13 sessions:

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

1. The CLI or TUI selects a durable session and creates one process-local
   execution-session manager.
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
- `background_tasks.py` owns process-local execution sessions, incremental
  output, health checks, events, and cleanup.
- `capability_config.py`, `plugins.py`, `skills.py`, and `capabilities.py` own
  user configuration, local packages, lazy instructions, and MCP lifecycle.
- `provider.py` implements complete and streaming OpenRouter Responses calls.
- `parser.py` extracts text, tool calls, and valid memory citations.
- `tools.py` contains built-in tools and the session-level registry abstraction.

## Security and Scope Boundaries

Storage directories and files receive restrictive permissions where the host
supports them. Raw logs may contain prompts and tool results, so users must
treat `CODING_KID_HOME` as sensitive and use soft deletion deliberately.

Version 13 does not add encryption at rest, remote synchronization, vector
search, persistent or remote processes, process reconnection after restart,
remote Agent graphs, automatic dependency/image construction, a workflow DSL,
a Plugin marketplace, OAuth, or non-tool MCP primitives. Docker, its daemon,
its image, and the host-side control plane remain trusted; the sandbox does not
defend against a compromised daemon or container-kernel escape.
