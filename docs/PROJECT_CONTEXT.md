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
- Version 14 isolated collaboration and Web research has completed
  implementation and verification and awaits user completion confirmation.
  Child Agents default to application-owned Git worktrees with dirty-root
  baselines, bounded visible context forks, cwd-bound execution, persistent
  manifests, diff/reconcile/integrate/confirmed-discard, and V12 checkpoint
  acceptance/rollback. Brave search and public-text fetch are bounded,
  attributable external tools with pinned public-address connections, safe
  redirects, approval, workflow, and sandbox-network enforcement. V13 is frozen
  in the installed runtime and V14 is the living default. It passes 420 of 421
  tests with one Windows symlink skip, Ruff, ten worktree and Docker stress
  rounds, wheel inspection, clean-install V1-V14 launches, and direct installed
  CLI/TUI trials. No benchmark or paid request ran. See
  `docs/reports/v14-verification.md`.
- Version 13 continuous execution environment has completed implementation and
  verification. One bounded manager owns short, yielded, background,
  and interactive commands; Windows ConPTY/Unix PTY sessions accept later input
  and Ctrl+C, output is incremental with temporary full logs, readiness checks
  run in the same host/container environment, and child Agents receive private
  managers that close with the child run. V12 is frozen and the launcher selects
  V1-V13 with V13 as the living default. It passes 397 tests with one Windows
  symlink skip, Ruff, ten real Docker stress rounds, wheel inspection,
  clean-install V1-V13 launches, direct installed-wheel terminal trials, and
  real `openai/gpt-5.6-luna` REPL/service/Cautious workflows. The live work
  retained 54 completed model responses and remained conservatively below USD
  0.75. Its standalone archive passes 338 tests with one Windows symlink skip
  on Python 3.11 and 3.13, Ruff, wheel inspection, and clean installation. The
  user confirmed completion on 2026-08-06; it is archived under
  `versions/13-continuous-execution-environment/` with annotated tag
  `version-13-continuous-execution-environment`.
- Version 12 permission-governed workflow is complete and archived under
  `versions/12-permission-governed-workflow/` with annotated tag
  `version-12-permission-governed-workflow`. It
  separates collaboration mode, approval policy, and the existing sandbox;
  adds application-owned approval prompts and conflict-aware stage checkpoints;
  freezes V11; and makes V12 the installed default. It passes 383 tests with one
  Windows symlink skip, Ruff, ten stress rounds, wheel inspection, clean-install
  V1-V12 launches, and installed-wheel TUI trials. At most 18 short paid model
  responses kept estimated spend below USD 0.10. No benchmark ran.
- Version 11 sandbox control is complete and archived under
  `versions/11-sandbox-control/` with annotated tag
  `version-11-sandbox-control`.
  The Docker-backed default `workspace-write`, `read-only`, and explicit
  `danger-full-access` policies cover built-in file tools, foreground commands,
  background tasks, and child Agents without changing the V10 loop. V10 is
  frozen in the installed runtime; 309 tests, Ruff, Docker probes and cleanup
  stress, wheel inspection, clean-install V1-V11 launches, and real installed-
  wheel TUI trials pass. Eleven paid responses remained conservatively below
  USD 0.05; no benchmark was run. The user confirmed stage completion on
  2026-08-05.
- Version 10 controllable-turn-runtime is complete and archived under
  `versions/10-controllable-turn-runtime/` with annotated tag
  `version-10-controllable-turn-runtime`. It makes
  Turn/Step transitions explicit, adds bounded active-turn steering, preserves
  protocol evidence for completed side effects across interruption, propagates
  cancellation into foreground work, and adds controlled safe-tool scheduling.
  It passes 289 tests, Ruff, ten rounds of concurrency/process cleanup stress,
  final wheel inspection, clean-install V1–V10 launches, and real TUI steering,
  hard-interrupt, evidence-resume, and FIFO trials. Eight paid responses kept
  task-wide live spend conservatively below USD 0.02; no benchmark was run.
  The user selected the research topic, delegated implementation plus
  deterministic and bounded real-TUI verification, and confirmed stage
  completion on 2026-08-05. Version 09 remains the frozen teaching checkpoint.
- Version 09 multi-Agent workflows are complete and archived under
  `versions/09-multi-agent-workflows/` with annotated tag
  `version-09-multi-agent-workflows`. One root-owned `AgentManager` runs up to
  four isolated child
  Agent loops concurrently, retains 16 process-local records, and exposes
  strict spawn/list/poll/wait/followup/stop operations. Children share cwd,
  Skills, and MCP but not root history, memory, todos, compaction state,
  background tasks, or nested-Agent tools. CLI/TUI controls and notifications
  do not wake the model. V08 is frozen in the installed runtime and the launcher
  selects V1–V9 with V09 as the default. It passes 273 tests, Ruff, 10-round
  four-worker
  stress, final wheel inspection, V08 source fidelity, clean-install V1–V9
  launches, and three real parallel/followup/stop scenarios. The complete live
  run used USD 0.011379095. The user explicitly confirmed stage completion.
- Version 08 is complete and archived under `versions/08-background-tasks/`
  with annotated tag `version-08-background-tasks`. Explicit process-local
  background shell tasks survive Agent turns through one bounded
  application-owned manager.
  The model can start, list, poll, wait for, and stop tasks; the CLI and TUI add
  direct task controls and lifecycle notifications. Tasks are not persistent,
  do not wake the model, and are cleaned up with their process trees on exit.
  Version 07 is frozen in the installed historical runtime and the launcher now
  selects V1–V8 with V08 as the default. It passes 254 tests, Ruff, 10-round
  concurrency/process-tree stress, wheel and clean-install verification, and a
  real Unicode background/wait/stop session whose instrumented final run cost
  USD 0.00116478. The user explicitly confirmed stage completion.
- Version 07 is complete and archived under
  `versions/07-pluggable-capabilities/` with tag
  `version-07-pluggable-capabilities`: a user-configured, session-scoped
  pluggable capability runtime combining on-demand Skills, namespaced local
  Plugins, and
  stdio/Streamable HTTP MCP tools. The user explicitly delegated implementation
  and verification to the assistant. Sandbox, approvals, marketplaces, OAuth,
  non-tool MCP primitives, multi-agent work, and generic background tasks are
  excluded. It passed 213 deterministic tests, Ruff, wheel inspection,
  fresh-install V1–V7 launches, and one minimal real Skill-to-MCP verification.
  A corrective checkpoint hardens the Windows foreground terminal boundary
  after a real Skill A/B run exposed a GBK display crash. It passes 223 root
  tests, 187 standalone-archive tests, Ruff, fresh-wheel V07 launch, and an
  installed-wheel Unicode round trip. The final checkpoint is tagged
  `version-07-pluggable-capabilities-fix2`; neither the original tag nor the
  intermediate `fix1` tag is moved.
  A subsequent real `openai/gpt-5.6-luna` CLI smoke passed Unicode PowerShell,
  recoverable command failure, self-correction, and separate Unicode Python
  stdout/stderr without modifying its isolated project.
- Version 06 is complete and archived under `versions/06-persistent-memory/`.
  Its corrected checkpoint, tagged `version-06-persistent-memory-fix1`, keeps
  restored tool history provider-safe, refuses ineffective or contradictory
  compaction, and renders terminal-only streamed answers reliably. It passed
  180 deterministic tests, Ruff, 10 rounds of concurrency stress, wheel
  inspection, and fresh-install V1–V6 verification without a paid request. The
  subsequent real `openai/gpt-5.6-luna` TUI verification passed tool-history
  resume, failed-compaction rollback, interruption recovery, final rendering,
  and cross-session automatic memory extraction, consolidation, search, and
  recall for about USD 0.00133 total. The original
  `version-06-persistent-memory` tag remains unchanged.
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
- An unnumbered cross-version launcher improvement is complete. Each version
  transition extends its registry; Version 13 selects Versions 01–13, bundles
  frozen V01–V12, and defaults to the living Version 13 runtime. The original
  V1–V3 increment passed
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
- Version 05 implementation and deterministic verification are complete. It is
  a simplified Codex-style full-screen terminal UI with streamed assistant text,
  typed lifecycle events, and visualizations for the existing todo, tool, and
  context-management state. It passed 140 tests, Ruff, wheel inspection, and
  fresh-install V1–V5 launches without a paid model request.
- Version 05 remains session-local and does not add background tasks, multi-agent
  work, skills, plugins, MCP, permissions, sandboxing, or persistent traces.
- Version 05 is complete and archived under `versions/05-streaming-tui/` with
  annotated tag `version-05-streaming-tui`.
- The user explicitly delegated implementation and verification of Version 05
  to the assistant.
