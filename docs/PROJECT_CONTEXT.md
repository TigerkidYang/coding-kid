# Coding Kid Project Context

## Purpose

Coding Kid is a hands-on project for building a Python coding agent from
scratch.

The immediate objective is to implement a sequence of complete, understandable
versions. Only the current version matters during implementation. The contents
of later versions are intentionally left undecided until the user is ready to
start them.

## Working Model

The project follows an implementation-first, one-version-at-a-time workflow:

1. The user decides what the next version should contain.
2. The version's scope and completion criteria are recorded.
3. Relevant source code and technical questions are researched as needed.
4. The user implements the version with the assistant acting as tutor and
   thinking partner.
5. The agent maintains small, coherent local commits throughout the work.
6. The version is verified and archived under `versions/` with a matching Git
   tag when the user declares it complete or starts the next version.
7. Only then is the following version discussed.

There is no standing roadmap for later versions.

The root project on `main` is the continuously evolving implementation. See
`docs/VERSIONING.md` for the complete Git and teaching-archive policy.

## Research Role

Source-code research remains part of the project because implementation may
depend on understanding how mature Coding Agents solve specific problems.

Research is driven by the needs of the current version. Existing reports under
`docs/reports/` remain available, and `docs/RESEARCH.md` can be extended when a
concrete implementation question requires it.

## Article Status

Article work is inactive. Existing drafts under `docs/articles/` are preserved
without further development. Writing and publishing will resume only when the
user explicitly chooses to return to them.

## Collaboration Model

The user is the project lead and sole implementer of project code unless a
specific task is explicitly delegated.

The assistant acts as:

- Research assistant for source-code and technical questions relevant to the
  current version.
- Coding tutor who explains structure, logic, and tradeoffs.
- Thinking partner who helps the user define version scope and completion
  criteria.
- Execution assistant for concrete file or operational changes when directly
  requested.

The assistant must not choose future version contents or write project code
without explicit permission.

## Current State

- The project is named Coding Kid. Its repository/distribution identifier is
  `coding-kid`, and its Python package is `coding_kid`.
- The canonical repository is
  `https://github.com/TigerkidYang/coding-kid`.
- Version 01 is complete and archived under `versions/01-minimal-agent/` with
  tags `version-01-minimal-agent` and `version-01-minimal-agent-fix2`.
- Version 02 is complete: session-scoped task decomposition via a `todo` tool.
  It passed 52 unit tests, lint/format checks, and the hardened live todo smoke.
- The user explicitly delegated implementation of Version 02 to the assistant.
- Evaluation for this stage: Verified × 10 is the SWE bugfix baseline (V01 and
  cleaned V02 both 5/10). Primary Todo evidence is the goal-only multi-step
  slice in `evals/v02-baseline/todo_slice/` (see `TODO_SLICE.md` and
  `todo_slice/SCORECARD.md`).
- Git and completed-version archive management is defined in
  `docs/VERSIONING.md`.
- Research notes and reports are available for use during implementation.
- Article drafts are preserved but inactive.
