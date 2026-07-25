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
Version 01 is complete. Version 02 is defined in `docs/TASKS.md` as
session-scoped task decomposition via a `todo` tool. Agents wait for the user
to choose later versions before those begin.

## Keep Version 02 todos session-scoped and replace-based

Decision:
Version 02 adds one `todo` tool that replaces the full checklist on each call.
State lives in process memory beside conversation history, rolls back with
failed CLI turns, and is injected into model instructions when non-empty.
Statuses are `pending`, `in_progress`, and `completed`, with at most one
`in_progress` item. `activeForm`, Plan Mode, Glob/Grep, and disk persistence
are out of scope.

Consequence:
Task decomposition stays a small, teachable tool addition on top of the Version
01 loop instead of introducing a planning mode or durable task database.

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
Execute at most 12 model-requested tools in one user turn. Provide a matched
skipped result for later calls and explicitly instruct the model to answer from
evidence already collected. Guide broad repository-overview requests toward a
small, selective evidence set.

Consequence:
A model cannot turn a simple overview into an unbounded recursive inspection or
large parallel batch. Skipped calls preserve the provider's function-call
protocol without appearing in the terminal as completed work.
