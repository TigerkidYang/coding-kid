# AGENTS.md

This file is the handoff contract for AI agents working on this repository.
Read it at the start of every new chat before changing files.

## Project Goal

This project is being rebuilt from scratch.

The long-term goal is to make each future AI chat able to understand the project
without repeating the same background conversation. Keep project knowledge in
versioned files, not only in chat history.

## Memory System

Use these files as the project's durable memory:

- `AGENTS.md`: entry point for agents, workflow rules, and memory policy.
- `README.md`: human-facing project overview, setup, and usage.
- `docs/PROJECT_CONTEXT.md`: product intent, users, scope, and current status.
- `docs/ARCHITECTURE.md`: technical design, module boundaries, data flow, and tradeoffs.
- `docs/DECISIONS.md`: important decisions with date, context, decision, and consequence.
- `docs/TASKS.md`: active backlog, next actions, and known open questions.

If a file does not exist yet, create it when the information becomes useful.
Do not create empty documentation just to satisfy the list.

## Start-of-Chat Routine

At the beginning of any substantial task, an agent should:

1. Read `AGENTS.md`.
2. Check `git status --short --branch`.
3. Read the relevant memory files under `docs/`.
4. Inspect the files directly related to the requested work.
5. Make a small, concrete plan before editing when the change is non-trivial.

For tiny tasks, keep the routine proportional.

## Updating Memory

Update durable memory when a change affects future work, especially when:

- The project goal, audience, or constraints change.
- A major design or technical decision is made.
- A new convention, dependency, service, or workflow is introduced.
- A task is completed, blocked, deferred, or split into follow-up work.
- A future agent would otherwise need chat history to understand what happened.

Prefer short, factual notes over long narrative. Link to code paths when useful.

## What Not To Store

Do not store:

- Secrets, API keys, tokens, passwords, cookies, or private credentials.
- Large logs or generated output.
- Temporary reasoning that will not matter after the current task.
- Personal data unless it is explicitly part of the project requirements.

Secrets belong in local environment files that are ignored by Git.

## Git Workflow

- Keep commits small and named clearly.
- Check `git status` before and after edits.
- Do not overwrite user changes unless explicitly asked.
- Prefer documenting important project decisions in `docs/DECISIONS.md` before
  or alongside the implementation that depends on them.

## Documentation Style

- Write documentation in English unless the user asks for Chinese.
- Keep sections skimmable.
- Use concrete paths, commands, and examples.
- When facts become outdated, update or remove them instead of adding conflicting notes.

## Current State

- Repository was cleared on 2026-06-29 for a fresh rebuild.
- Remote `origin/main` was also cleared and now matches the local empty project baseline.
- No application architecture has been chosen yet.

