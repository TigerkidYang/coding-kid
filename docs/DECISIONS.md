# Decisions

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
Versions 01 through 04 are complete. Version 05 is the current Streaming TUI
implementation. Do not define a later version until Version 05 is complete.

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
`coding-kid v1` through `v5` work from any project directory without
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
an explicit error. Commit conversation-history changes only after a turn
finishes successfully, and roll back failed or interrupted CLI turns.

Consequence:
The terminal never presents a blank `Coding Kid>` response as success, and an
incomplete provider response cannot corrupt the following conversation turn.

## Bound tool calls as well as tool output

Decision:
Execute at most 12 model-requested file/shell tools in one user turn. Todo
checklist updates are excluded from that budget. Provide a matched skipped
result for later non-todo calls and explicitly instruct the model to answer from
evidence already collected. Guide broad repository-overview requests toward a
small, selective evidence set.

Consequence:
A model cannot turn a simple overview into an unbounded recursive inspection or
large parallel batch. Skipped calls preserve the provider's function-call
protocol without appearing in the terminal as completed work. Planning with
`todo` does not reduce the budget available for real work.
