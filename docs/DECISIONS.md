# Decisions

## Treat benchmark feedback as one maintenance version

Decision:
Package the cross-cutting fixes exposed by Terminal-Bench 2.1 as Version 15,
without inventing a new headline feature or adding task-specific behavior. Keep
the official verifier outcome as the ability boundary, retry only classified
infrastructure failures, and report the result as k=1 for the complete 89-task
set.

Consequence:
Resource bounds, usable-tool filtering, non-Git checkpoints, provider
compatibility, and resumable evaluation operations form one auditable
maintenance checkpoint. The 50/89 result is reproducible evidence for the
Coding Kid V15 plus Luna pairing, but it is not presented as directly
equivalent to k=5 or pass@k leaderboard data. Future development may analyze
the clean timeout and verifier-zero subsets, but must not overfit task-specific
solutions into the general runtime.

## Unify Version 13 commands as process-local execution sessions

Decision:
Register every root command with one bounded execution-session manager before
waiting. Use pipes for non-interactive work and a real ConPTY/Unix PTY only when
`interactive=true`. Treat explicit background as immediate yield, preserve a
live process after ordinary yield or turn interruption, and keep health checks
as separate commands in the same host/container environment.

Consequence:
Short, yielded, background, and interactive work share identity, incremental
output, limits, events, permission, sandbox, and cleanup. Later input cannot
bypass V12 approval; Ctrl+C is not stop; liveness is not readiness. Root IDs do
not survive restart, and child Agents receive private managers that are always
closed when the child run ends.

On Windows, set `PYTHON_BASIC_REPL=1` for interactive environments. Python
3.13's enhanced REPL corrupts non-BMP input through ConPTY, while the basic
REPL preserves the same Unicode behavior verified on Python 3.11. Other
interactive programs ignore this Python-specific compatibility variable.

## Keep Version 12 collaboration, approval, and sandbox policies independent

Decision:
Represent collaboration mode (`plan`, `implementation`, or `review`), approval
policy (`cautious`, `auto`, or `full-access`), and the Version 11 sandbox policy
as separate session inputs. Enforce collaboration restrictions and hard safety
checks before consulting approval state; an approval may authorize an action but
can never widen its sandbox.

Consequence:
Plan and Review cannot mutate the project even under `full-access` approval, and
`read-only` remains non-writable even when no approval prompt is required. V12
can explain every denial in terms of the correct layer instead of treating Plan
mode as a sandbox alias.

## Make Version 12 approval and rollback application-owned

Decision:
Place a single permission broker before tool dispatch and keep one-shot/session
grants process-local. Store approved plans and bounded project checkpoints in
the durable session/application control plane, never in model-writable project
paths. Refuse rollback on recorded external conflicts or while child/background
work is active.

Consequence:
No model tool executes while its approval is pending, stale prompt responses are
harmless, and process restart clears implicit trust. Rollback preserves the
pre-stage dirty worktree but intentionally excludes ignored output, external
effects, and conflicting concurrent edits.

This file records decisions that govern current and future work. Replace or
remove entries when they no longer describe the project.

## Name the project Coding Kid

Decision:
Use `Coding Kid` as the human-facing project name, `coding-kid` for repository
and distribution identifiers, and `coding_kid` for the future Python import
package.

Consequence:
Documentation and UI copy use `Coding Kid`. Future repository URLs, package
metadata, commands that require a distribution name, and archive references use
`coding-kid` where applicable. Python source paths and imports use `coding_kid`.
Generic references to the broader coding-agent category remain descriptive and
are not replaced with the project name.

## Use repository files as project memory

Decision:
Use `AGENTS.md` as the entry point and the files under `docs/` as durable project
memory.

Consequence:
Agents read the relevant memory before substantial work and keep it aligned with
the current project state.

## Build one complete version at a time

Decision:
The project is implementation-first. Define, implement, verify, and commit one
version before discussing the next one.

Consequence:
Do not maintain a multi-version roadmap or add speculative future capabilities
to current tasks and architecture.

## Define each version immediately before implementation

Decision:
The user decides each version's goal, scope, exclusions, and completion criteria
when that version is about to begin.

Consequence:
Versions 01 through 11 are complete. Do not define a later version until the
user chooses one from the research topic list.

## Make Version 11 sandbox policy explicit and fail closed

Decision:
Select one immutable startup policy: `read-only`, `workspace-write`, or
`danger-full-access`, defaulting to `workspace-write`. Restricted model shell
commands run only through a Docker Linux container and all built-in file tools
share one project-root path policy. Docker or image failure rejects restricted
startup; the model cannot request a host fallback or policy elevation.

Consequence:
The provider, session store, and inert Skill loader remain application control
plane services on the host. Restricted modes do not start MCP servers or expose
MCP tools because their local or remote effects cannot be proven contained.
Network is disabled unless the user opts in at startup. Per-command approvals,
automatic unsandboxed retries, and domain proxies remain outside Version 11.
Docker and the configured image are trusted infrastructure; Version 11 does not
claim protection from a compromised daemon or kernel escape.

## Make complete protocol rounds the Version 10 evidence boundary

Decision:
Keep the root loop synchronous, but represent its steps, recoveries, budgets,
stalls, steering, interruption, and terminal paths with explicit reasons and
events. Retain complete tool-call/output rounds and their side effects across
failure or interruption; discard incomplete assistant streams and roll back
temporary compaction projections only. Queue active-TUI input FIFO and use
reasoned cancellation to distinguish steering from hard interruption.

Consequence:
Users can redirect active work without losing input or completed evidence, and
persistent resume remains provider-protocol safe. Recovery and continuation are
bounded and inspectable. This does not provide general rollback, durable
in-flight execution, a workflow DSL, hooks, or autonomous wakeups.

## Parallelize only explicitly safe Version 10 tools

Decision:
Allow bounded overlap only for consecutive tool calls whose registry entries
explicitly declare `parallel_safe`. Mark built-in `read` and `search`; default
every stateful, external, dynamically supplied, and unknown tool to exclusive.
Preserve model call order when committing results.

Consequence:
Independent repository reads can reduce latency without allowing concurrent
writes or silently trusting third-party capabilities. An exclusive call is a
barrier between safe batches, at most four safe calls execute concurrently,
and adding a tool never grants parallel execution by accident.

## Keep Version 09 child Agents process-local and root-owned

Decision:
Create one `AgentManager` per Coding Kid application process and keep the root
Agent loop synchronous. Child Agents run independent `run_turn` calls on
bounded worker threads, share cwd and application capabilities, and expose
results only through explicit poll/wait/followup operations. Completion emits
state and UI events but never wakes the model.

Consequence:
Four children may run concurrently and 16 records remain addressable. Child
conversation, compaction, todos, and tool budgets are isolated; root history
and long-term memory are not copied. Children cannot nest Agents or launch
background shell work. Their IDs and transcripts do not survive a process
restart, and Version 09 provides no file isolation or overlapping-write merge,
so delegation prompts must partition write ownership.

## Treat terminal execution as a byte and process-lifecycle boundary

Decision:
Run living-runtime Windows commands through non-interactive PowerShell with
Unicode-safe encoded input and explicit UTF-8 output. Capture bounded byte
streams, decode with deterministic fallback, return partial timeout evidence,
terminate descendant processes, and isolate output-codec failures from Agent
state.

Consequence:
The terminal no longer depends on the host GBK/ANSI code page, a noisy command
cannot consume unbounded capture memory, and a timeout is recoverable evidence
instead of an exception with discarded output. Version 08 reuses this boundary
for explicit background tasks, but still does not add PTY input, sandboxing, or
approvals.

## Keep Version 08 background work explicit and process-local

Decision:
Create one `BackgroundTaskManager` per Coding Kid application process. The model
must explicitly set `execute(..., background=true)`, and uses one `task` tool to
list, poll, wait for, or stop work. Keep the synchronous Agent loop: completion
adds a bounded UI event and a dynamic next-step summary, but never wakes the
model. Treat `wait` as process completion only; readiness requires output or a
health probe.

Consequence:
Background processes survive turn rollback but not application restart. IDs,
processes, output, and notifications are not persisted or remembered. Eight
running tasks, 32 retained records, 256,000 bytes per stream, a 30-second wait,
and bounded UI/prompt queues define the resource envelope. Windows background
processes use a kill-on-close Job Object in addition to the shared terminal
boundary so concurrent stop and shutdown reclaim descendants and readers.

## Compose Version 07 capabilities at session startup

Decision:
Capture Skill and Plugin metadata at process startup, connect only MCP servers
explicitly listed in the user-owned capability configuration, and expose all
selected capabilities through one session-owned runtime and tool registry.
Keep Skill bodies lazy and reload capabilities on process resume rather than
persisting executable configuration or credentials in session logs.

Consequence:
Project Skills can provide inert instructions without causing startup code
execution. Plugins package namespaced Skill roots and MCP configuration but do
not create a separate execution mechanism. The synchronous teaching loop stays
intact while one dedicated async runtime owns MCP clients and subprocesses.
Sandboxing, approval workflows, remote installation, OAuth, MCP resources and
prompts, and background reconnect remain outside Version 07.

## Make JSONL canonical and SQLite queryable for Version 06 sessions

Decision:
Store each session as an append-only, hash-chained JSONL log and use
project-scoped SQLite for indexes, leases, and memory metadata. Commit transcript
deltas plus a complete bounded active-state snapshot at successful turn and
compaction boundaries. Treat JSONL as authoritative and repair rebuildable
SQLite metadata after crashes.

Consequence:
Session history remains inspectable and deterministic without quadratic
transcript snapshots. Partial tails, stale indexes, concurrent writers, and
mid-file corruption have explicit recovery or refusal behavior. Session resume
restores the original cwd, model, project instructions, todos, compaction state,
and accounting rather than silently adopting a different runtime snapshot.

## Normalize provider protocol items before persistence and replay

Decision:
Convert SDK response objects to provider-input JSON as they enter conversation
state, recursively omit optional null fields, and re-normalize restored items
for compatibility with original V06 logs. Commit compaction only when it reduces
the request estimate, and reject summaries that contradict deterministic tool
evidence.

Consequence:
Function-call and reasoning history can cross JSON and process boundaries
without relying on SDK object identity or output-only null fields. Existing V06
logs remain readable. Ineffective or evidently contradictory compaction fails
atomically and leaves the prior active context available.

## Separate exact sessions from selective long-term memory

Decision:
Use four layers: raw session evidence, per-session structured extraction,
consolidated typed memory, and bounded request-only recall. Run extraction and
consolidation as validated no-tools model calls with cursors, leases, provenance,
and atomic promotion. Generate only project memory automatically; require an
explicit command for cross-project user memory.

Consequence:
Long-term memory is intentionally lossy while session persistence remains
lossless. Recall never enters transcript or compaction history, does not require
a vector database, and treats memory as potentially stale evidence. Hidden
citations update usage only for memories actually used. Automatic maintenance
is bounded and configurable without completing the separate generic
background-task research topic.

## Model Version 05 on the Codex TUI event boundary

Decision:
Use a simplified Codex-style full-screen layout: session card, single scrolling
transcript, working status, composer, and footer. Represent assistant deltas,
complete messages, tools, todos, compaction, completion, interruption, and
failure as typed events from a synchronous worker. Keep non-TTY plain mode and
use the complete terminal provider response as the only source for parsing and
canonical commits.

Consequence:
Version 05 visualizes existing state without a sidebar or new agent capability.
Streaming UI history is not model history. Tool calls wait for the complete
response, failed and interrupted turns retain Version 04 rollback, and
compaction summaries remain non-streaming and hidden. Future capabilities can
add event projections without coupling their state to Textual widgets.

## Manage Version 04 context as canonical state plus an active view

Decision:
Keep the full real conversation transcript in process memory while maintaining
a separate bounded active context for model requests. Classify the latest user
request and complete recent model/tool rounds as retained context, summarize
older active history at safe protocol boundaries, and regenerate stable
session/project context and dynamic todo/recovery guidance from their canonical
sources. The handoff must classify actions and evidence as completed or pending,
and the continuation wrapper treats that classification as authoritative so a
retained original request does not make the model repeat completed tool work.

Consequence:
Compaction does not erase the session transcript or turn synthetic request
context into conversation history. A successful compaction atomically replaces
only the active view; failed and interrupted turns restore both views and todo
state. Version 04 remains session-local and does not introduce persistence,
long-term memory, skills, plugins, MCP, or multiple compaction tiers.

## Use measured usage with a conservative context-window fallback

Decision:
Prefer an explicit `CODING_KID_CONTEXT_WINDOW`, otherwise discover the current
OpenRouter model's `context_length` once per session. Use provider input-token
usage to calibrate a conservative local estimate. If model metadata is
unavailable, continue in passive mode with manual compaction and one reactive
context-limit recovery rather than inventing a window size.

Consequence:
Proactive compaction has a defensible budget and remains testable. Metadata
failure does not prevent ordinary use, while `/context` makes the degraded mode
visible.

## Install all completed teaching runtimes together

Decision:
Use one `coding-kid` installation and one dependency environment for every
completed teaching version. A positional teaching-version argument selects the
runtime, while no argument selects the latest completed core version. Bundle
historical runtime source inside the distribution and execute it in an isolated
child Python process; execute the latest living runtime directly.

Consequence:
`coding-kid v1` through `v8` work from any project directory without
installing separate conflicting distributions or duplicating dependencies. The
teaching labels are separate from the distribution's package release number.
Completed archives remain read-only provenance and are not imported at runtime;
bundled copies are checked against them. Future version transitions must freeze
the just-completed runtime into the bundle and advance the launcher registry.

## Keep Version 02 todos session-scoped and replace-based

Decision:
Version 02 adds one `todo` tool that replaces the full checklist on each call.
State lives in process memory beside conversation history, rolls back with
failed CLI turns, and is injected into model instructions when non-empty.
Statuses are `pending`, `in_progress`, and `completed`, with at most one
`in_progress` item. Lists are bounded to 20 items of 200 characters each and
may be cleared with an empty update. New chats start empty, fully completed
lists are cleared after success, and a final answer gets one reconciliation
retry while an item remains `in_progress`. `activeForm`, Plan Mode, Glob/Grep,
and disk persistence are out of scope. Todo calls do not consume the per-turn
file/shell tool budget.

Consequence:
Task decomposition stays a small, teachable tool addition on top of the Version
01 loop instead of introducing a planning mode or durable task database.
Planning updates cannot starve the 64-call budget used for real work, grow
without bound, leak into a new chat, or silently report an active step as
finished.

## Assemble Version 03 context in explicit layers

Decision:
Version 03 captures one immutable session context containing runtime facts and
project instructions. It discovers the nearest Git root and loads only
`AGENTS.md` files from that root to the current working directory. Project
instruction contents share a 32 KiB root-first budget, are labeled by source,
and enter model input as a synthetic contextual user message. Base behavior and
runtime facts form the stable instruction prefix; todos and recovery guidance
are rendered as dynamic suffixes for each model step.

Consequence:
Large model input becomes bounded, testable, and source-aware without turning
project documentation into Coding Kid's own system policy or duplicating it in
conversation history. The project intentionally postpones global instructions,
fallback filenames, conditional rules, dynamic reload, context compression,
skills, plugins, MCP, and persistent memory.

## Prefer domestic Docker mirrors with explicit prefix pulls for SWE-bench

Decision:
Configure Docker `registry-mirrors` for ordinary Hub images, but treat SWE-bench
`sweb.eval.*` pulls as a separate path: pull through an explicit domestic mirror
prefix (currently `docker.1ms.run/...`) and retag to the official
`swebench/sweb.eval...` name the harness expects. Validate this with
`evals/v02-baseline/smoke_docker_mirror.py` before any full harness run.

Consequence:
Evaluation no longer depends on discovering broken mirror fallback during a
multi-GB Verified × 10 run. Images can be pre-pulled and kept with
`--cache_level instance`.

## Test agent and eval infrastructure before scoring

Decision:
Before spending a full online evaluation budget, run unit tests, a live agent
smoke for the current version feature, Docker mirror smoke, image pre-pull, and
optionally a one-instance harness smoke.

Consequence:
Broken tools, prompts, mirrors, or harness wiring are caught before the expensive
Verified × 10 scoring pass.

## Use research to support the current implementation

Decision:
Keep existing source-code research active as reference material and perform new
research when the current version raises a concrete question.

Consequence:
Research remains available throughout implementation but is not managed as an
independent parallel track.

## Keep implementation and authorship user-led

Decision:
The user is the sole implementer of project code and sole author of final
article text unless a specific task is explicitly delegated.

Consequence:
Agents research, explain, discuss, and perform requested operational work without
taking over implementation or authorship.

## Keep article work inactive

Decision:
Preserve existing article drafts without developing or publishing them while the
implementation is the active focus.

Consequence:
Article tasks and article-specific Git workflows do not appear in the active
project workflow. They resume only on explicit user direction.

## Keep a living main implementation and browsable version archives

Decision:
Use `main` for the continuously evolving root implementation. Preserve every
completed major version as an independently understandable and runnable copy
under `versions/NN-short-name/`, with a matching annotated tag named
`version-NN-short-name`.

Consequence:
Git commits retain the development history, while stable repository paths make
historical code easy to inspect, compare, and cite in teaching material. Archived
versions are read-only and must not become dependencies of current code.

## Delegate routine local version management to the agent

Decision:
The agent automatically creates coherent local commits during implementation
and performs the archive-and-tag procedure when the user declares a version
complete or begins the next one.

Consequence:
The user does not need to repeat these Git instructions in later chats. Pushes,
history rewrites, tag movement or deletion, and destructive cleanup still
require explicit permission. The complete policy is in `docs/VERSIONING.md`.

## Keep Version 01 minimal and function-based

Decision:
Build Version 01 as a synchronous terminal agent with one OpenRouter provider,
an in-memory message list, a direct model/tool loop, and ordinary Python tool
functions stored in an explicit registration dictionary.

Consequence:
Version 01 does not introduce multiple API-provider abstractions, tool classes,
streaming, persistence, planning, sandboxing, or TUI infrastructure. It includes
only the structure required to teach and demonstrate a complete coding-agent
workflow.

## Keep raw tool results inside the agent loop

Decision:
Show each tool's action and target in the terminal, but keep successful raw
results inside the model context. Show the complete result only when it is an
error.

Consequence:
Users can follow what the agent is doing without printing file contents, search
matches, command output, write content, or patch text. This is a presentation
rule in `cli.py`; tool behavior and model context remain unchanged.

## Bound tool results before they enter model context

Decision:
Cap every tool result at 50,000 characters. Reject an empty search query, skip
common generated directories and files larger than 1 MB, and return at most 100
matches from one search tool call.

Consequence:
An accidental broad search, large file read, or noisy command cannot overwhelm
the next model request. Truncated results are marked so the model can narrow its
next action.

## Never accept an empty final answer

Decision:
Retry one isolated empty model response and turn repeated empty responses into
an explicit error. In Version 10, commit each complete model/tool protocol round
as evidence. On failure or interruption, retain those rounds and their todo
effects while discarding incomplete assistant streaming text and temporary
compaction projections.

Consequence:
The terminal never presents a blank `Coding Kid>` response as success, and an
incomplete provider response cannot corrupt the following conversation turn.
Completed side effects remain paired with the outputs needed for safe resume.

## Bound tool calls as well as tool output

Decision:
Execute at most 64 model-requested file/shell tools in one user turn. Todo
checklist updates are excluded from that budget. Provide a matched skipped
result for later non-todo calls and explicitly instruct the model to answer from
evidence already collected. Guide broad repository-overview requests toward a
small, selective evidence set.

Consequence:
A model cannot turn a simple overview into an unbounded recursive inspection or
large parallel batch. Skipped calls preserve the provider's function-call
protocol without appearing in the terminal as completed work. Planning with
`todo` does not reduce the budget available for real work.
## Isolate writing child Agents in application-owned Git worktrees

Decision:
Version 14 defaults child Agents to Git worktrees managed under protected
session state. Capture the root's tracked and non-ignored dirty content as a
private baseline, commit only the child's later delta, and require parent-owned
diff, reconcile, integrate, or confirmed discard operations. Keep explicit
`shared` isolation only for compatibility and intentionally safe tasks.

Consequence:
Parallel children may modify overlapping paths without cross-contamination or
root mutation. Integration is a whole-patch action under the existing stage
checkpoint; conflicts stay in isolation, rollback preserves retryable work, and
acceptance cleans only validated application-owned paths and branches.

## Fork only bounded visible conversation context to children

Decision:
Let a spawn request select zero to eight recent user/visible-assistant rounds,
bounded to 24,000 characters. Never fork tool calls, tool outputs, hidden
reasoning, long-term memory, or pending protocol state.

Consequence:
Children can inherit just enough intent for a delegated task without cloning
unsafe provider protocol or silently expanding context and privacy scope.

## Keep Web research GET-only, public-only, and attributable

Decision:
Use a fixed Brave Search endpoint for discovery and an application-owned
public-text fetcher for HTTP(S) standard ports. Validate every DNS answer and
redirect as globally routable, pin the socket to the validated address, bound
bytes/text/redirects/results, reject encoded and binary bodies, and label all
external content as untrusted with source URLs.

Consequence:
Current external information becomes available in all collaboration modes under
external-effect approval and the immutable sandbox network policy, without
introducing browser automation, authenticated browsing, arbitrary downloads,
or an SSRF path. Environments whose DNS intentionally maps public names to
reserved addresses fail closed.
