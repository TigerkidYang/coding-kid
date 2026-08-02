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
- Version 02 is archived under `versions/02-task-decomposition/` with annotated
  tag `version-02-task-decomposition`.
- Version 03 is complete: bounded, session-stable context assembly with
  hierarchical project `AGENTS.md` instructions. It passed 68 deterministic
  tests, the paired context slice at 6/6 process and 6/6 outcome, and the
  official SWE-bench Verified × 10 regression check at 7/10.
- Version 03 is archived under `versions/03-context-assembly/` with annotated
  tag `version-03-context-assembly`.
- An unnumbered cross-version launcher improvement is complete. Version 04 now
  extends its registry so one installation selects Versions 01–04 and defaults
  to the living Version 04 runtime. The original V1–V3 launcher increment passed
  91 deterministic tests plus fresh-wheel launches from an unrelated project
  directory; the launcher itself has no version archive or tag.
- The user explicitly delegated this launcher improvement to the assistant.
- Version 04 is complete: single-session bounded context management. It separates
  the complete in-memory transcript from the model-visible active context and
  adds window accounting, protected/recent history policy, compaction, and
  recovery without adding persistence or long-term memory.
- Version 04 passes 115 deterministic tests, maintained-source Ruff checks,
  wheel inspection, and fresh-install V1–V4 launches. Its bounded live batch
  passed the paired V04 process and outcome slice at 3/3. The first CLI smoke
  exposed a continuation loop after real compaction; the handoff contract was
  hardened, and a separately authorized retry passed process and outcome using
  6/60 requests. It is archived under `versions/04-context-management/` with
  annotated tag `version-04-context-management`.
- The user explicitly delegated implementation and verification of Version 04
  to the assistant.
- The user explicitly delegated implementation of Version 03 to the assistant.
- The user explicitly delegated implementation of Version 02 to the assistant.
- Evaluation for Version 03 is under `evals/v03-context-assembly/`: the paired
  context slice passed at 6/6 process and 6/6 outcome versus Version 02's 4/6
  outcome, and the secondary Verified × 10 score was 7/10.
- Git and completed-version archive management is defined in
  `docs/VERSIONING.md`.
- Research notes and reports are available for use during implementation.
- Article drafts are preserved but inactive.
- No Version 05 is currently defined.
