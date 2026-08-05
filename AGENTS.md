# AGENTS.md

This file is the handoff contract for AI agents working on this repository.
Read it at the start of every new chat before changing files.

## Project Goal

Build Coding Kid, a Python coding agent, from scratch, one complete version at a
time.

The project is implementation-first. Do not create a multi-version roadmap in
advance. Before work begins on a version, the user will decide what that version
should contain. Finish and verify that version before defining the next one.

## Memory System

Use these files as the project's durable memory:

- `AGENTS.md`: entry point, workflow rules, and memory policy.
- `README.md`: human-facing overview, setup, and usage once a runnable version
  exists.
- `docs/PROJECT_CONTEXT.md`: current purpose, working model, and scope.
- `docs/ARCHITECTURE.md`: architecture of the current implementation once one
  exists.
- `docs/DECISIONS.md`: decisions that govern current and future work.
- `docs/TASKS.md`: the current version and its immediate work only.
- `docs/VERSIONING.md`: Git commits, version archives, tags, and the delegated
  automation rules for version transitions.
- `docs/RESEARCH.md`: source-code research notes used to support implementation.
- `docs/CONTENT_STRATEGY.md`: status and rules for the inactive article work.

If a file does not exist yet, create it when its information becomes useful. Do
not create empty documentation just to satisfy the list.

## Start-of-Chat Routine

At the beginning of any substantial task:

1. Read `AGENTS.md`.
2. Check `git status --short --branch`.
3. Read `docs/PROJECT_CONTEXT.md`, `docs/TASKS.md`, and the other memory files
   relevant to the task.
4. Read `docs/VERSIONING.md` before implementation work or any Git operation.
5. Inspect the files directly related to the requested work.
6. Make a small, concrete plan before editing when the change is non-trivial.

Keep the routine proportional for tiny tasks.

## Version Workflow

Work on exactly one version at a time.

### Research-topic gate for version discussions

`docs/RESEARCH.md` -> `Research Topic List` is the sole starting point and
scope framework for every new-version discussion. The agent must not invent a
version theme or propose capabilities outside that list on its own.

Whenever the user starts discussing a new version, the agent's first response
must:

1. Read the current `Research Topic List` from `docs/RESEARCH.md` rather than
   relying on memory.
2. Reproduce the complete list in both English and Chinese.
3. Mark every topic with a checkbox showing whether it is already completed or
   still incomplete, based on the repository's current implementation and
   durable project records.
4. Use that bilingual, status-marked list as the basis for the discussion. Do
   not suggest or select the new version's contents before presenting it.

The user chooses which incomplete research topic, if any, becomes the new
version. The agent may explain the listed topics and their tradeoffs, but has no
authority to choose a topic or introduce an unlisted one.

Before implementing a version:

1. Discuss that version with the user.
2. Record its goal, included scope, excluded scope, and completion criteria.
3. Research only the source code and technical questions needed for that
   version.
4. Do not define later versions.

During implementation:

- Keep work inside the agreed scope.
- Make a small local commit after each coherent, verified increment according to
  `docs/VERSIONING.md`.
- Use research as implementation support, not as a separate deliverable track.
- Update architecture and decisions only when the current version makes them
  concrete.
- Do not begin article work.

Before moving on:

1. Verify the current version against its completion criteria.
2. Follow the complete archive procedure in `docs/VERSIONING.md`.
3. Update durable memory to reflect the resulting state.
4. Wait for the user to define the next version.

## Collaboration Boundary

The user is the project lead, sole implementer of project code, and sole author
of final article text unless they explicitly delegate a specific action.

Agents should support the user by:

- Researching relevant source code and unresolved technical questions.
- Explaining concepts, implementation details, and tradeoffs.
- Helping define the scope and completion criteria of the current version.
- Acting as a thinking partner while the user implements the code.
- Performing concrete operational tasks only when explicitly asked.
- Automatically maintaining local Git history and completed-version archives
  within the authority defined in `docs/VERSIONING.md`.

Agents must not assume permission to:

- Write or modify project code on the user's behalf.
- Draft or revise final article prose on the user's behalf.
- Decide the contents of a version before the user chooses them.
- Create a roadmap for later versions.
- Turn conversational wording into formal goals, automations, or task-tracking
  state unless the user explicitly asks for that tooling.

Routine local commits, completed-version snapshots, and annotated version tags
are standing delegated responsibilities under `docs/VERSIONING.md`; they do not
require the user to repeat the authorization each time. Once the user explicitly
confirms that a stage is complete, that confirmation also authorizes a normal
non-force push of the completed work and its version tags according to
`docs/VERSIONING.md`. Rewriting history, deleting or moving tags, and other
destructive Git operations remain outside that standing authorization.

## Benchmark and Spending Authorization

Do not run SWE-bench, including inference, prediction generation, smoke runs,
subsets, reruns, or the official evaluation harness, unless the user explicitly
authorizes that specific run.

For ordinary implementation, bug-fix, and post-fix verification tasks that the
user has explicitly requested, live model-inference verification is standing
authorized up to **USD 1.00 per user-requested task**, with no request-count
limit. Track the task's cumulative spend, stop before exceeding USD 1.00, and
use the smallest useful live run after deterministic checks pass. This standing
authorization includes real CLI/TUI smoke tests, tool-use continuation,
persistent-session resume, compaction, interruption recovery, and long-term
memory verification when they are in scope of the requested task.

Do not start any benchmark or batch evaluation that can consume paid API
credits unless the user explicitly authorizes that specific run and its
spending scope. Do not exceed the standing USD 1.00 verification allowance for
an ordinary task without a new explicit authorization.

An approved plan, version completion criterion, earlier benchmark request,
available credentials, or an existing evaluation script is not authorization
for a benchmark or batch run. Reading existing reports and running ordinary
local unit, lint, or format checks that do not invoke a paid model remain
allowed.

## Research

Existing research under `docs/RESEARCH.md` and `docs/reports/` remains available
and active as reference material. Read or extend it when a concrete question in
the current version requires it.

Do not conduct broad research merely to advance a separate research track.

## Article Work

Article work is inactive while the implementation is being built. Preserve
existing drafts under `docs/articles/`, but do not extend, edit, publish, or
create article-specific Git checkpoints unless the user explicitly resumes that
work.

## Updating Memory

Update durable memory when a change affects future work, especially when:

- The current version is defined or completed.
- Its scope or completion criteria change.
- An architecture or technical decision becomes concrete.
- A task is completed, blocked, or removed from the current version.
- A future agent would otherwise need chat history to understand the current
  state.

Keep notes short and factual. Replace outdated statements instead of preserving
a narrative of superseded plans.

## What Not To Store

Do not store:

- Secrets, API keys, tokens, passwords, cookies, or private credentials.
- Large logs or generated output.
- Temporary reasoning that will not matter after the current task.
- Speculative plans for future versions.
- Personal data unless it is explicitly part of the project requirements.

Secrets belong in ignored local environment files.

## Git Workflow

Follow `docs/VERSIONING.md` as the authoritative Git and version-archive policy.
In particular:

- Keep commits small, coherent, and clearly named.
- Keep `main` as the continuously evolving implementation.
- Preserve each completed major version under `versions/` and with an annotated
  Git tag.
- Do not overwrite user changes or mix unrelated work into a commit.
- After the user confirms a stage is complete, push its completed commits and
  version tags normally. Never force-push or perform destructive Git operations
  without separate explicit permission.

## Documentation Style

- Write documentation in English unless the user asks for Chinese.
- Keep sections skimmable.
- Use concrete paths, commands, and examples.
- Update or remove outdated facts instead of adding conflicting notes.

## Current State

- Version 10 is complete and archived under
  `versions/10-controllable-turn-runtime/` with annotated tag
  `version-10-controllable-turn-runtime`. Explicit Turn/Step phases, reasons,
  limits, recovery, FIFO TUI steering, hard interruption, completed-round
  evidence retention, foreground cancellation, and bounded safe-tool
  parallelism now control the living synchronous root loop. V09 is frozen in
  the installed runtime and the launcher selects V1–V10 with V10 as default. It
  passes 289 tests, Ruff, ten rounds of concurrency/process-tree stress, wheel
  inspection, and clean-install V1–V10 launches. Real
  `openai/gpt-5.6-luna` TUI steering, interruption, persistence, FIFO, process
  cleanup, and retained-evidence recall passed in eight paid responses for
  conservatively less than USD 0.02. No SWE-bench or paid batch evaluation was
  run. The user confirmed stage completion on 2026-08-05. See
  `docs/reports/v10-live-verification.md`.
- Version 09 is complete and archived under
  `versions/09-multi-agent-workflows/` with annotated tag
  `version-09-multi-agent-workflows`. A root-owned bounded
  `AgentManager` provides true parallel child runs plus list/poll/wait/followup/
  stop, isolated child conversation/compaction/todos/budgets, restricted child
  tools, CLI/TUI state and notifications, and cancellation evidence without
  changing the synchronous root loop. V08 is frozen in the installed runtime;
  the launcher selects V1–V9 with V09 as default. It passes 273 tests, Ruff,
  10-round four-worker stress, final wheel/V08 fidelity/clean-install checks,
  and three real `openai/gpt-5.6-luna` workflows for USD 0.011379095 total. The
  user explicitly confirmed stage completion.
- The project is named Coding Kid.
- Version 08 is complete and archived under
  `versions/08-background-tasks/` with annotated tag
  `version-08-background-tasks`. An application-owned bounded
  background-task manager supports explicit background `execute`, unified
  list/poll/wait/stop operations, CLI/TUI controls and notifications, dynamic
  model summaries, and deterministic process-tree cleanup without changing the
  synchronous Agent loop. V07 is frozen in the installed historical runtime,
  and the launcher now selects V1–V8 with V08 as the default. The user
  explicitly delegated implementation and verification to the assistant. It
  passes 254 deterministic tests, Ruff, 10-round concurrency and process-tree
  stress, final wheel inspection, clean-install V1–V8 launches, and a real
  background/wait/stop run. The instrumented final live run cost USD 0.00116478;
  all live attempts remained below USD 0.01 total. The user explicitly
  confirmed stage completion.
- Version 07 implementation and verification are complete: session-scoped
  Skills, explicitly enabled local Plugins, and stdio/Streamable HTTP MCP tools
  share one bounded per-turn registry without changing the synchronous Agent
  loop. It passed 213 deterministic tests, Ruff, wheel inspection,
  fresh-install V1–V7 launches, and one minimal real Skill-to-MCP verification.
  The user explicitly delegated implementation and verification to the
  assistant. It is archived under `versions/07-pluggable-capabilities/` with
  annotated tag `version-07-pluggable-capabilities`.
  The corrective terminal-boundary checkpoint uses Unicode-safe PowerShell,
  bounded byte capture, decode fallback, process-tree cleanup, partial timeout
  results, and codec-safe CLI rendering. It passes 223 root tests, 187 archive
  tests, Ruff, and fresh-wheel verification. The final checkpoint is tagged
  `version-07-pluggable-capabilities-fix2`; the original and intermediate
  `fix1` tags remain unchanged.
  A subsequent real `openai/gpt-5.6-luna` CLI smoke passed multilingual and
  emoji PowerShell output, recoverable command failure, model self-correction,
  and separate Unicode Python stdout/stderr in an unchanged isolated project.
- Version 06 is complete: persistent multi-session state plus layered long-term
  memory. The corrective checkpoint normalizes replayed provider protocol
  items, rejects ineffective or tool-contradicting compaction, and fixes
  terminal-only TUI answers. It passed 180 deterministic tests, Ruff, 10 rounds
  of concurrency stress, wheel inspection, and fresh-install V1–V6 launches
  without a paid request. A real `openai/gpt-5.6-luna` TUI verification then
  passed tool use, provider-safe resume, failed-compaction rollback, interruption
  recovery, terminal-only rendering, and cross-session automatic memory
  extraction/consolidation/search/recall for about USD 0.00133 total. It is
  archived under `versions/06-persistent-memory/`; the original tag remains
  `version-06-persistent-memory` and the correction is tagged
  `version-06-persistent-memory-fix1`.
- The user explicitly delegated implementation and deterministic verification
  of Version 06 to the assistant.
- Version 01 is complete as a minimal terminal coding agent and is archived
  under `versions/01-minimal-agent/` (`version-01-minimal-agent`,
  `version-01-minimal-agent-fix2`).
- Version 02 is complete: it adds a session-scoped `todo` tool for task
  decomposition and is archived under `versions/02-task-decomposition/` with
  tag `version-02-task-decomposition`.
- Version 03 is complete: bounded, session-stable context assembly with
  hierarchical project `AGENTS.md` loading. It is archived under
  `versions/03-context-assembly/` with tag `version-03-context-assembly`.
- An unnumbered cross-version launcher improvement is complete. Version 06 now
  extends it so one installation selects Versions 01–06 and defaults to the
  living Version 06 runtime. The launcher itself has no version archive or tag.
- Version 04 is complete: single-session bounded context management with
  separate canonical transcript and model-visible active context, window
  accounting, compaction, and recovery. It is archived under
  `versions/04-context-management/` with tag
  `version-04-context-management`.
- The user explicitly delegated implementation and verification of Version 04
  to the assistant.
- The root project contains the living implementation, tests, and usage
  documentation.
- Version 05 implementation and deterministic verification are complete: a
  simplified Codex-style full-screen Streaming TUI over the existing todo,
  tool, and context-management state. It passed 140 tests, Ruff, wheel
  inspection, and fresh-install V1–V5 launches without a paid request.
- Version 05 is complete and archived under `versions/05-streaming-tui/` with
  annotated tag `version-05-streaming-tui`.
- The user explicitly delegated implementation and verification of Version 05
  to the assistant.
- Existing source-code research is available to support implementation.
- Existing article drafts are preserved, and article work is inactive.
