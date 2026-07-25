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
require the user to repeat the authorization each time. Pushing, rewriting
history, deleting or moving tags, and other destructive Git operations remain
outside that standing authorization.

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
- Do not push or perform destructive Git operations without explicit permission.

## Documentation Style

- Write documentation in English unless the user asks for Chinese.
- Keep sections skimmable.
- Use concrete paths, commands, and examples.
- Update or remove outdated facts instead of adding conflicting notes.

## Current State

- The project is named Coding Kid.
- Version 01 is complete as a minimal terminal coding agent and is archived
  under `versions/01-minimal-agent/` (`version-01-minimal-agent`,
  `version-01-minimal-agent-fix2`).
- Version 02 is active: add a session-scoped `todo` tool for task decomposition.
  Details are in `docs/TASKS.md`.
- The root project contains the living implementation, tests, and usage
  documentation.
- Existing source-code research is available to support implementation.
- Existing article drafts are preserved, and article work is inactive.
