# Tasks

## Current Core Version: 11 — Sandbox Control

Completion status: in progress. The user selected the final incomplete research
topic, "How to control the sandbox environment," approved the implementation
plan, and explicitly delegated development, deterministic verification, and a
real installed-wheel TUI trial to the assistant.

### Goal

Constrain model-controlled local file and process tools behind one explicit,
session-wide sandbox policy without changing the synchronous Turn/Step loop.
Restricted modes must confine work to the project, with no silent fallback to
the host when isolation is unavailable.

### Included Scope

- `read-only`, `workspace-write`, and `danger-full-access` startup modes, with
  `workspace-write` as the default.
- An application-owned Docker sandbox for restricted foreground/background
  commands, with bounded resources, filtered environment, explicit network
  control, and deterministic container cleanup.
- One canonical path policy for built-in read/search/write/patch/delete tools,
  including traversal, symlink/junction, and protected-metadata checks.
- The same policy inherited by child Agents and background tasks.
- Fail-closed startup diagnostics and explicit CLI/TUI sandbox status.
- Restricted-mode suppression of MCP processes and tools whose effects cannot
  be contained by the local sandbox; inert Skills remain available.
- V10 runtime freezing plus installed V1-V11 selection.
- Deterministic, Docker integration, stress, packaging, clean-install, and real
  TUI verification.

### Excluded Scope

- Per-command approvals, permission prompts, remembered approval rules, or
  model-requested escalation.
- Automatic unsandboxed retry, command allow/deny parsing, or trust scoring.
- Domain-level network proxies, remote service authorization, or sandboxing
  remote HTTP effects.
- Container-image construction, package-manager orchestration, VM lifecycle,
  or protection from a compromised Docker daemon or container kernel escape.
- SWE-bench or another paid batch evaluation.

### Completion Criteria

- Restricted modes never execute a model command on the host and refuse to
  start when Docker or the configured image is unavailable.
- `workspace-write` can modify the project but cannot read or write outside it;
  `read-only` cannot modify it; `.git` and `.coding-kid` remain protected.
- Host secrets are not inherited by sandbox commands, network is disabled by
  default, and the Docker socket is never mounted.
- Timeout, cancellation, background stop, Agent stop, and application shutdown
  leave no running Coding Kid containers while retaining bounded evidence.
- CLI/TUI expose the effective policy, backend, image, and network state; tool
  denials are model-readable and do not trigger a host retry.
- Pytest, Ruff, isolation probes, cleanup stress, wheel inspection, V10
  fidelity, clean-install V1-V11 launches, and a real TUI trial pass within the
  standing USD 1.00 live-verification allowance.

## Current Core Version: 10 — Controllable Turn Runtime

Completion status: complete and archived under
`versions/10-controllable-turn-runtime/` with annotated tag
`version-10-controllable-turn-runtime`. The user selected the advanced research
topic "How to better control the whole loop and workflow," delegated
implementation and verification, and confirmed stage completion on 2026-08-05.

### Goal

Replace the implicit collection of loop branches with a bounded, observable
Turn/Step control runtime. Active TUI work can be steered without dropping user
input or erasing evidence of completed side effects; continuation, recovery,
interruption, tool scheduling, and termination have explicit reasons.

### Included Scope

- Explicit turn phases, transition reasons, limits, counters, and one terminal
  outcome over the existing synchronous model/tool core.
- Complete model/tool rounds as commit boundaries, with protocol-closing
  aborted or skipped results when work is interrupted.
- A bounded FIFO active-turn input queue used by the Streaming TUI for steering.
- Cancellation propagated through provider requests, foreground processes,
  task/Agent waits, and tool scheduling.
- Observable provider recovery, repeated-action circuit breaking, completion
  validation, and structured control events.
- Bounded parallel execution for explicitly safe read/search calls while every
  stateful or externally supplied tool remains exclusive.
- Installed teaching-version selection for V1–V10, with V09 frozen before V10
  changes.
- Deterministic, stress, packaging, clean-install, and bounded real-TUI
  verification.

### Excluded Scope

- Sandbox or approval policy, arbitrary lifecycle hooks, a workflow DSL,
  durable in-flight steps, distributed queues, or remote workers.
- Autonomous model wakeups, scheduled work, speculative streaming-tool starts,
  general side-effect rollback, or dynamic multi-model routing.
- Nested Agent graphs, worktree merge automation, SWE-bench, or another paid
  batch evaluation.

### Completion Criteria

- Active TUI submissions are queued and consumed in FIFO order rather than
  silently discarded; hard interrupt and steering remain distinct.
- Completed tool effects retain matching protocol evidence across interruption
  and persistent-session resume, while incomplete streams are discarded.
- Foreground commands stop their process trees on turn cancellation and retain
  bounded partial evidence.
- Every continue, recovery, budget, stall, and terminal path is structured,
  bounded, visible, and emits exactly one terminal event.
- Safe tools demonstrate bounded overlap and ordered results; exclusive tools
  never overlap a safe batch.
- Pytest, Ruff, race/cleanup stress, wheel inspection, V09 fidelity,
  clean-install V1–V10 launches, and real TUI steer/interruption/resume trials
  pass within the standing USD 1.00 task cap.

### Verification Result

- The maintained suite passes **289 tests** in 97.55 seconds; Ruff lint and
  formatting checks pass over all maintained `src/` and `tests/` sources.
- Ten rounds of five concurrency and cleanup probes pass: safe-call overlap,
  exclusive barriers, FIFO TUI steering, hard interruption, and foreground
  process-tree cancellation. No delayed sentinel or surviving worker remains.
- The final wheel contains **143 files / 139 Python files**, frozen V01–V09
  runtimes, and living V10, with no tests, evaluations, `showcase/`, logs,
  caches, or bytecode. A clean Python 3.13 installation launches explicit
  V1–V10 and default V10 from an unrelated directory without a provider call.
- A real installed-wheel `openai/gpt-5.6-luna` TUI session passes soft steering
  of a foreground process, FIFO steering across continuations, hard interrupt,
  completed-write evidence retention, process cleanup, persistent resume, and
  no-tool recall of the retained write value. The first recall exposed an
  insufficient grounding instruction; the prompt was corrected, covered by a
  regression test, and the installed-wheel retry returned the exact retained
  value.
- The live trials used **8 paid responses**. Persisted snapshots recorded 17,070
  last-step input tokens in aggregate; because the provider cost is not stored,
  task-wide spend is conservatively estimated below **USD 0.02**, far below the
  USD 1.00 allowance. No SWE-bench or paid batch evaluation was run. See
  `docs/reports/v10-live-verification.md`.

## Current Core Version: 09 — Multi-Agent Workflows

Completion status: complete and archived under
`versions/09-multi-agent-workflows/` with annotated tag
`version-09-multi-agent-workflows`. The user explicitly confirmed stage
completion on 2026-08-05.

### Goal

Add a bounded process-local multi-agent control plane without replacing the
synchronous root Agent loop. The root Agent can start independent child Agents
in parallel, inspect or wait for them, continue an existing child, stop work,
and synthesize returned evidence.

### Included Scope

- One application-owned `AgentManager` with bounded concurrency, retained
  records, results, progress, events, cancellation, and shutdown.
- Strict `spawn_agent` plus unified `agent` list/poll/wait/followup/stop tools.
- Fresh child contexts with isolated conversation, compaction, todo state, and
  budgets; shared project context, cwd, Skills, MCP, and user permissions.
- Root CLI/TUI status commands and notifications without autonomous model
  wakeups.
- Installed teaching-version selection for V1–V9, with V08 frozen before V09
  changes.
- Deterministic, concurrency, packaging, clean-install, and bounded real-model
  verification.

### Excluded Scope

- Nested or peer-to-peer Agents, arbitrary Agent graphs, roles, model
  overrides, and parent-history forks.
- Durable child transcripts, cross-process Agent resume, long-term-memory
  extraction from child runs, or remote Agents.
- Worktrees, containers, sandboxing, approvals, overlapping-write merging, and
  background shell tasks inside child Agents.
- Autonomous model wakeups, proactive delegation modes, SWE-bench, or another
  paid batch evaluation.

### Completion Criteria

- The root Agent can launch at least two actually overlapping child runs, wait
  for their results, and synthesize them in its normal tool loop.
- Follow-up work reuses the selected child's context; wait timeout, failure,
  cancellation, stop, retention, and application shutdown remain bounded and
  truthful.
- Root and child conversation, compaction, todos, tool budgets, and rollback
  are isolated; child registries contain Skills/MCP but no Agent or background
  task tools.
- CLI/TUI expose current state and terminal notifications without completion
  initiating a provider request.
- Pytest, Ruff, 10-round concurrency/cleanup stress, wheel inspection,
  fresh-install V1–V9 launches, and bounded real parallel/follow-up/stop trials
  pass within the standing USD 1.00 task cap.

### Verification Result

- 273 deterministic tests pass; Ruff check and format check pass over maintained
  `src/` and `tests/` sources.
- The 10-round, four-worker stress test reaches exactly four-way overlap with
  no excess concurrency, duplicate terminal event, todo leak, deadlock, or
  surviving worker thread. A real cancelled foreground command retains partial
  evidence and leaves no delayed sentinel.
- The final wheel contains 121 files and frozen V01–V08 plus living V09, with no
  tests, evals, research, `showcase/`, logs, or caches. Frozen V08 matches its
  archive across 20 runtime files. A clean Python 3.13 installation launches
  explicit V1–V9 and default V09 from an unrelated cwd without a model call.
- Three clean-wheel `openai/gpt-5.6-luna` scenarios pass: overlapping research,
  same-Agent implementation/followup with independently confirmed 10-test
  result, and foreground stop/partial evidence/process cleanup/session resume.
  All 51 paid requests, including one retained non-passing cancellation attempt,
  used 117,376 input and 5,411 output tokens for USD 0.011379095. See
  `docs/reports/v09-live-verification.md`.

## Current Core Version: 08 — Background Tasks

Completion status: complete and archived under `versions/08-background-tasks/`
with annotated tag `version-08-background-tasks`. The user explicitly confirmed
stage completion.

### Goal

Add process-local, cross-turn background shell tasks without changing the
synchronous Agent loop. The model explicitly chooses background execution and
can list, poll, wait for, or stop a task through one bounded task runtime.

### Included Scope

- An optional `background` flag on `execute`; foreground behavior remains the
  Version 07 Unicode-safe, bounded, two-minute command boundary.
- A session-owned background task manager with random IDs, explicit lifecycle
  states, bounded stdout/stderr, concurrency and retention limits, process-tree
  cleanup, completion events, and deterministic shutdown.
- A `task` tool with `list`, `poll`, `wait`, and `stop` actions. Waiting is
  bounded and cancellable without terminating the task.
- Dynamic model-visible task status plus `/tasks` and `/task stop <id>` in the
  plain CLI and Streaming TUI.
- Installed teaching-version selection for V1–V8, with V07 frozen before V08
  changes.
- Deterministic, concurrency, packaging, fresh-install, and one bounded real
  model verification.

### Excluded Scope

- Automatic backgrounding, implicit readiness detection, PTY or stdin input,
  autonomous model wakeups, scheduled work, and generic remote jobs.
- Background task survival across Coding Kid process restarts or persistence in
  sessions and long-term memory.
- Multi-agent workflows, sandboxing, approvals, and changes to MCP connection
  lifecycle.
- SWE-bench or any paid batch evaluation.

### Completion Criteria

- Background `execute` returns immediately with a stable task ID while the
  process continues across Agent turns.
- The model and user can inspect and stop tasks; `wait` distinguishes a bounded
  wait timeout from process completion, and readiness requires concrete logs or
  a health probe.
- Task count, retained records, stdout/stderr, UI events, prompt summaries, and
  waits are bounded; normal application exit terminates every running process
  tree and drains readers.
- Interrupted or failed turns keep launched tasks discoverable while preserving
  existing conversation/context/todo rollback.
- Foreground execution, persistence, TUI, Skills, Plugins, MCP, historical
  launch selection, and packaging remain covered by deterministic tests.
- Pytest, Ruff, wheel inspection, fresh-install V1–V8 launches, concurrency
  stress, and one independently checked real background-task session pass.

### Verification

- Deterministic suite: **254 passed**, including process state/output bounds,
  wait cancellation, terminal eviction, provider-strict schemas, Agent rollback,
  Skill/MCP composition, CLI/TUI controls, lifecycle events, session behavior,
  and historical launcher fidelity.
- Concurrency and cleanup: **10/10** mixed start/wait/poll/stop/close stress
  rounds passed without state regression, duplicate terminal events, deadlock,
  lingering task threads, or running processes. A separate parent/child stop
  probe passed 10/10 rounds; the 60-second child sentinel remained absent.
- Ruff lint and formatting checks for maintained `src/` and `tests/`: passed.
- Final wheel: **100 files / 96 Python files**, including frozen V01–V07 and
  living V08. It contains no tests, evaluations, research trees, `showcase/`,
  caches, bytecode, or logs.
- A clean temporary installation launched explicit V1–V8 and default V08 from
  an unrelated directory without a provider request.
- A real `openai/gpt-5.6-luna` run explicitly backgrounded a Unicode worker,
  read independent evidence before waiting, captured separate stdout/stderr,
  then started and stopped a parent/child process tree. CLI notifications,
  `/tasks`, tool order, and persisted protocol evidence matched the run. After
  shutdown, related process count was zero immediately and after 15 seconds;
  the delayed sentinel did not appear.
- The instrumented final live run used **8 model steps, 11,820 input tokens,
  547 output tokens, and USD 0.00116478**. Earlier fixture/schema attempts kept
  the task-wide live spend conservatively below USD 0.01, far below the USD 1
  cap. No SWE-bench or paid batch evaluation was run.

## Current Core Version: 07 — Pluggable Capabilities

Completion status: complete and archived under
`versions/07-pluggable-capabilities/` with annotated tag
`version-07-pluggable-capabilities`. The user explicitly delegated
implementation and verification to the assistant.

### Goal

Add a session-scoped capability runtime in which Skills provide on-demand
instructions, MCP servers provide structured tools, and explicitly enabled
Plugins package namespaced Skills and MCP configuration.

### Included Scope

- User and hierarchical project `SKILL.md` discovery with bounded metadata,
  deterministic precedence, explicit `$skill` mentions, and an implicit
  `skill` loading tool.
- Strict user-owned `capabilities.json` configuration for explicitly enabled
  local Plugins and standalone MCP servers.
- A minimal Plugin manifest that contributes contained, namespaced Skill roots
  and MCP server configuration.
- Session-owned stdio and Streamable HTTP MCP clients, bounded tool discovery,
  synchronous dispatch bridging, cancellation, timeout, and cleanup.
- Capability status in the plain CLI and Streaming TUI, plus a local example
  Plugin and deterministic end-to-end tests.
- Installed teaching-version selection for V1-V7, with V06 frozen before V07
  changes.

### Excluded Scope

- Sandboxing, approvals, isolation, marketplaces, download/update, signing,
  OAuth, or credential storage.
- MCP Resources, Prompts, SSE, WebSocket, Sampling, Elicitation, Roots,
  subscriptions, dynamic refresh, deferred tool search, or background reconnect.
- Hooks, Apps, LSP, multi-agent workflows, or generic background tasks.
- SWE-bench or paid batch evaluation.

### Completion Criteria

- Skills are discovered with the recorded precedence and budgets; explicit and
  model-selected Skills load complete source-labeled content without entering
  durable history unless invoked through the tool protocol.
- Explicitly configured Plugins safely contribute namespaced Skills and MCP
  servers without allowing manifest paths to escape their roots.
- Optional MCP failures degrade visibly, required failures stop startup, and
  stdio/Streamable HTTP tools can be discovered, filtered, called, cancelled,
  bounded, and closed.
- Agent requests, compaction, context accounting, CLI/TUI rendering, and session
  resume use one consistent capability snapshot without persisting credentials.
- Deterministic tests, maintained-source Ruff checks, wheel inspection, and
  fresh-install V1-V7 launches pass before one bounded live verification.

### Verification

- Deterministic suite: **213 passed**, including Skill discovery/loading,
  Plugin containment and namespaces, strict configuration, stdio and
  Streamable HTTP MCP, filtering, collision rejection, result normalization,
  timeout, cancellation, optional/required failure, cleanup, and the complete
  Skill → MCP → final-answer protocol.
- Ruff lint and formatting checks for maintained `src/` and `tests/`: passed.
- Fresh wheel: **79 files / 75 Python files**, including frozen V01–V06
  runtimes and the living V07 capability modules; no tests, evaluations,
  caches, bytecode, or logs entered the wheel.
- Fresh temporary installation launched explicit V1–V7 and default V07 from an
  unrelated directory without a provider request.
- One real `openai/gpt-5.6-luna` session explicitly loaded the bundled example
  Plugin Skill, called its read-only namespaced MCP tool, and returned the
  independently verified README measurements (348 lines / 14,456 characters).
  It stayed well below the USD 1.00 task cap.
- No SWE-bench or paid batch evaluation was run.

### Corrective Checkpoint: Terminal Boundary

- A real Skill A/B run exposed a Windows GBK crash while displaying `✳`.
- Source comparison with Codex and Claude Code led to a boundary-wide fix:
  Unicode-safe PowerShell input/UTF-8 output, bounded byte-first capture,
  deterministic decode fallback, CLIXML error normalization, non-interactive
  stdin, partial timeout evidence, process-tree cleanup, and codec-safe CLI
  rendering.
- The corrected root suite passes **223 tests** and Ruff checks. The corrected
  standalone V07 archive passes **187 tests** and Ruff checks.
- The fresh wheel contains `coding_kid/terminal.py`; a fresh unrelated-directory
  V07 launch and installed-wheel `✳` round trip pass without a provider request.
- The original and intermediate `fix1` tags remain unchanged; the final
  cleanup-hardened correction is tagged
  `version-07-pluggable-capabilities-fix2`.
- A post-tag real `openai/gpt-5.6-luna` CLI session then exercised five actual
  `execute` calls: multilingual/emoji PowerShell output, a missing command with
  exit code 1, successful recovery, and separate Unicode Python stdout/stderr.
  The model noticed its first Python newline was literal and corrected the
  command with `chr(10)`. All expected exit codes and text were preserved, the
  isolated project stayed empty, and no Skill, Plugin, MCP server, benchmark,
  or additional paid batch was involved. The failed credential-discovery
  launch made no provider request; the one bounded live session remained under
  the standing USD 1.00 cap.

## Current Core Version: 06 — Persistent Sessions and Long-Term Memory

Completion status: complete and archived under
`versions/06-persistent-memory/` with annotated tag
`version-06-persistent-memory`. The corrective checkpoint is tagged
`version-06-persistent-memory-fix1`; the original tag remains unchanged.

### Goal

Add deterministic project-scoped multi-session persistence and a layered
long-term-memory pipeline so Coding Kid can resume exact working state and
selectively carry useful knowledge into later sessions.

### Included Scope

- Hash-chained append-only JSONL session logs with SQLite metadata, leases,
  crash recovery, replay, listing, resumption, and soft deletion.
- Persistence of the canonical transcript, bounded active context, compaction
  checkpoints, todo state, model/context configuration, and accounting.
- Raw-session, per-session extraction, consolidated-memory, and bounded-recall
  layers with provenance and usage tracking.
- Project memories generated from eligible prior sessions and explicit global
  user memories only when the user requests them.
- Request-only memory retrieval, model-visible provenance, citation parsing,
  manual memory controls, and bounded automatic maintenance.
- Plain terminal, Streaming TUI, launcher, packaging, documentation, and
  deterministic verification updates for Version 06.

### Excluded Scope

- Generic background-task APIs, multi-agent workflows, skills/plugins, MCP,
  vector databases, remote synchronization, or encryption at rest.
- Automatic cross-project extraction, silent deletion of raw sessions, or
  memory facts treated as authoritative without freshness checks.
- SWE-bench and paid benchmark evaluation. Ordinary bounded live verification
  follows the standing authorization in `AGENTS.md`.

### Completion Criteria

- Multiple sessions in one project can be created, listed, resumed, and kept
  independent across process restarts.
- Resume deterministically restores transcript, active context, todos,
  compaction checkpoints, and context accounting from validated durable state.
- Partial writes, stale indexes, concurrent resumes, persistence failures, and
  corrupt records fail safely without silently damaging recoverable history.
- Eligible prior sessions can produce validated, provenance-linked memories;
  relevant memories are bounded and injected only into request context.
- Users can inspect, add, search, forget, synchronize, and disable memory, with
  automatic cross-project memory prohibited.
- Existing behavior and V1–V5 launch selection remain covered; pytest, Ruff,
  wheel inspection, and fresh-install V1–V6 launches pass without a paid call.

### Verification

- Deterministic suite: **180 passed**, covering provider-safe tool-history
  replay, hash corruption,
  partial writes, orphan-index recovery, leases, persistence retry, memory
  extraction/consolidation, recall isolation, citations, CLI/TUI commands, and
  all earlier behavior.
- Concurrency stress: **10 rounds / 40 grouped checks** covering simultaneous
  resume contention, parallel independent-session commits, memory-pipeline
  exclusion, and interruption/final-render event ordering.
- Ruff lint and formatting checks for maintained `src/` and `tests/`: passed.
- Fresh wheel: **61 files / 57 Python files**, including the frozen V05 runtime
  and living V06 `sessions.py` and `memory.py`; no tests, evaluations, caches,
  or bytecode entered the wheel.
- Fresh temporary installation launched explicit V1–V6 and default V06 from an
  unrelated project directory. Installed V06 session listing and `--continue`
  also passed without a provider request.
- Installed-wheel tool-history persistence/resume passed with a deterministic
  fake provider.
- Real `openai/gpt-5.6-luna` TUI verification passed actual read-tool use,
  provider-safe tool-history resume across restarts, safe rejection and rollback
  of ineffective compaction, resume after that rollback, interruption recovery,
  terminal-only final rendering, and automatic cross-session memory extraction,
  consolidation, search, and recall. Persisted sessions were closed and
  undamaged, with no turn-error records or null optional protocol fields. Total
  recorded spend was about **USD 0.00133**.
- No paid benchmark or SWE-bench run was performed for the correction.

## Current Core Version: 05 — Streaming TUI

Completion status: complete and archived under `versions/05-streaming-tui/`
with annotated tag `version-05-streaming-tui`.

### Goal

Build a simplified Codex-style full-screen terminal interface that streams
assistant text and makes Coding Kid's existing conversation, todo, tool, and
context-management lifecycle visible without changing canonical agent state.

### Included Scope

- A Textual full-screen interface for interactive terminals with a session
  header, single-column transcript, composer, working status, and footer.
- A non-TTY fallback that preserves the Version 04 plain terminal workflow.
- OpenRouter Responses API text streaming with a complete final response for
  parser, tool protocol, usage accounting, and transcript commits.
- Typed turn, assistant, tool, todo, compaction, completion, interruption, and
  failure events between the agent worker and UI.
- Codex-style user, assistant, exploration, edit, command, error, and Updated
  Plan transcript cells.
- Existing `/context`, `/compact`, `/exit`, and `/quit` behavior plus cooperative
  Esc/Ctrl+C interruption and Version 04 rollback.
- Deterministic provider, agent, TUI, launcher, wheel, and fresh-install tests.

### Excluded Scope

- Reasoning display, streamed tool arguments, queued input, attachments,
  mentions, shell mode, mouse interaction, themes, or a Web UI.
- Background tasks, multi-agent workflows, skills, plugins, MCP, approvals,
  sandboxing, session persistence, trace files, or production telemetry.
- Forced termination of an already-running synchronous tool.
- SWE-bench, paid benchmarks, or live provider calls without separate explicit
  authorization.

### Completion Criteria

- Interactive V05 launches a full-screen Codex-style interface; non-TTY V05 and
  all historical versions remain launchable from arbitrary project directories.
- Text deltas update one active assistant cell and consolidate exactly once from
  the complete response before parser/tool processing continues.
- Todo, tool, context, and compaction activity is readable and reflects real
  canonical state without exposing successful raw tool output.
- Stream errors, missing terminal responses, cancellation, failed compaction,
  and failed turns preserve Version 04 transcript/context/todo rollback.
- `/context`, `/compact`, `/exit`, `/quit`, Esc, Ctrl+C, narrow terminals, and
  passive context mode behave deterministically.
- Unit/integration/TUI tests, Ruff, wheel inspection, and fresh-install V1-V5
  launches pass without a paid request.

### Verification

- Deterministic suite: **140 passed**, including provider stream shapes, typed
  agent events, rollback, Textual Pilot flows, manual compaction, interruption,
  passive context, and 120×40, 80×24, and 40×10 terminal sizes.
- Ruff lint and formatting checks for maintained `src/` and `tests/`: passed.
- Fresh wheel: **48 files / 44 Python files**, including the 9-module frozen V04
  runtime and living V05 `tui.py`; no tests or cache files.
- Fresh temporary installation: explicit V1–V5, default V05, and the
  `coding-kid v5` console entry point all launched from an unrelated directory
  and exited without a provider request.
- An explicitly authorized live end-to-end session launched the installed
  `coding-kid` command in a real PTY against OpenRouter. It exercised multi-turn
  edits, todo history, pytest, streamed Markdown, `/context`, `/compact`, tool
  interruption, text-stream interruption, rollback, recovery, and `/exit`.
- No SWE-bench or benchmark was run.

## Current Core Version: 04 — Context Management

Completion status: complete and archived under
`versions/04-context-management/` with annotated tag
`version-04-context-management`.

### Goal

Add bounded single-session context management so Coding Kid can keep a full
in-memory transcript, build a smaller model-visible active context, account for
model-window pressure, compact older history at safe boundaries, and continue
the current task without losing canonical project or todo state.

### Included Scope

- Separate canonical transcript and model-visible active context.
- Complete user and model/tool segments with protocol-safe split boundaries.
- Explicit or OpenRouter-discovered context-window size, provider usage, and a
  conservative calibrated preflight estimate.
- Proactive compaction before and during turns, manual `/compact`, `/context`
  status, and one reactive context-limit recovery.
- Structured handoff summaries, latest-user preservation, recent-round
  retention, repeated compaction, atomic state replacement, and full turn
  rollback.
- Passive operation when model metadata is unavailable.
- Deterministic tests, wheel/install checks, and a focused V03/V04 live slice
  with one CLI smoke.
- Launcher selection for V1-V4 with V4 as the living default.

### Excluded Scope

- Persistent or cross-session history, long-term memory, transcript files, or
  retrieval.
- Multi-agent context, background compaction, skills, plugins, MCP, TUI, or
  provider abstraction.
- Claude Code-style microcompact, context collapse, cache editing, or multiple
  compression strategies.
- User-configurable summary prompts or separate summary models.
- SWE-bench or another broad paid benchmark.

### Completion Criteria

- Short sessions preserve Version 03 behavior and never compact unnecessarily.
- Window pressure is measurable and visible; missing metadata enters passive
  mode without blocking chat.
- Proactive and manual compaction produce one valid summary plus protected and
  budgeted recent context without splitting tool protocol pairs.
- Stable project context and dynamic todos are regenerated from canonical state
  after compaction.
- Failed summaries and failed/interrupted turns do not damage transcript,
  active context, or todo state.
- Repeated compaction stays bounded; explicit context-limit errors get at most
  one compact-and-retry recovery.
- Deterministic tests, Ruff checks, wheel inspection, and fresh-install V1-V4
  launches pass.
- The focused live slice passes V04 process and outcome at 3/3, does not regress
  below V03 outcome, and the CLI smoke completes with a real compaction within
  the authorized 30-request cap.

### Verification

- Deterministic suite: **115 passed** after the live-found continuation fix.
- Ruff lint and formatting checks for `src/`, `tests/`, and the V04 evaluation:
  passed. Historical evaluation fixtures retain pre-existing whole-repository
  Ruff findings and were not rewritten.
- Fresh wheel: 37 files, including 22 V1–V3 bundled runtime Python files and no
  tests, evaluations, caches, or logs. Default plus explicit V1–V4 launches
  passed from an unrelated temporary project.
- Authorized live batch on `openai/gpt-5.6-luna`: exactly **30/30** model
  requests; no SWE-bench. V03 outcome **3/3**, V04 process **3/3**, V04 outcome
  **3/3**, and repeated compaction completed twice as intended.
- The same batch's CLI smoke compacted successfully but failed its final outcome
  because the model repeatedly re-read evidence already captured by each
  handoff until the request cap stopped it. The implementation now labels
  completed tool actions and evidence as authoritative and explicitly forbids
  repetition caused only by the retained original request. Deterministic tests
  pass after that correction.
- The separately authorized post-fix CLI retry used **6/60** requests on the
  same model. It compacted once, reused the summarized evidence without
  rereading, wrote the exact requested result, verified it with a shell command,
  and completed. Process and outcome both passed. All Version 04 completion
  criteria are now satisfied on the living implementation.

## Completed Extra Improvement: Version-Selecting Launcher

Classification: unnumbered cross-version tooling, not a core version. The user
explicitly delegated implementation on 2026-08-02. Version 04 extends the
launcher registry while preserving the original improvement's design.

Completion status: verified. No version archive or tag is created for this
unnumbered improvement.

### Goal

Install Coding Kid once, then start any completed teaching version from an
arbitrary project directory by passing a version argument. With no argument,
start the latest version.

### Included Scope

- `coding-kid` and `python -m coding_kid` default to the living core runtime,
  currently Version 06.
- `coding-kid v1` through `v6` select the corresponding teaching runtime;
  numeric aliases such as `1` and `01` are accepted.
- Historical runtime source is bundled without tests, evaluation artifacts,
  lock files, caches, or separate dependency environments.
- Historical versions run in an isolated child Python process so their shared
  `coding_kid` import name cannot collide with the living implementation.
- The selected runtime inherits the caller's cwd, environment, terminal I/O,
  and exit status.
- Invalid versions fail before provider initialization and list the available
  versions.
- The version archive workflow records how every future completed version is
  bundled and registered before development advances.
- Deterministic tests cover selection, defaulting, isolation, source fidelity,
  wheel contents, and launch from an unrelated project directory.

### Excluded Scope

- Native executables, standalone installers, auto-update, package publishing,
  code signing, or a hosted release channel.
- Separate virtual environments or duplicated third-party dependencies per
  teaching version.
- Modifying completed archives or changing their existing tags.
- Model benchmarks, SWE-bench, paid capability evaluation, or live API smoke.
- Changes to the agent loop, tools, context assembly, provider, or model prompt.

### Completion Criteria

- One editable or wheel installation exposes a working `coding-kid` command.
- Omitting a version starts Version 06; explicit `v1` through `v6` select the
  requested runtime.
- A selected historical runtime starts with the caller's arbitrary project as
  its cwd and does not import modules from another teaching version.
- Bundled V1-V5 runtime files match their archived source snapshots, excluding
  launcher-management files from V04 and V05.
- Distribution inspection confirms all registered runtimes are present without
  tests, logs, caches, or additional copies of dependencies.
- README and architecture documentation explain installation, selection, and
  the distinction between package releases and teaching versions.
- `docs/VERSIONING.md` makes future launcher registration part of every version
  transition.
- Unit tests, integration tests, Ruff lint, and Ruff formatting checks pass
  without calling a paid model.

### Verification

- Current deterministic suite: **140 passed**.
- Ruff lint and formatting checks: passed.
- Built V05 wheel: 48 files, including 31 V1–V4 bundled runtime Python files.
- Wheel exclusions: 0 tests, evaluations, caches, or logs.
- Fresh temporary installation launched V1–V5, the V05 default, and the console
  entry point from an unrelated project directory; each exited locally without
  a provider call.

## Current Core Version: 03 — Context Assembly

Completion status: verified. The implementation, deterministic suite, paired
capability slice, and secondary regression check all passed. Archive and tag:
`versions/03-context-assembly/` and `version-03-context-assembly`.

### Goal

Add bounded, source-aware, session-stable input assembly so every model request
combines Coding Kid's base behavior, a runtime snapshot, hierarchical project
instructions, conversation history, and dynamic turn guidance without changing
the provider or tool-loop shape.

### Included Scope

- An immutable `SessionContext` captured once per terminal chat.
- Runtime context: absolute cwd, operating system, `cmd.exe`, configured model,
  and the local ISO date at session start.
- Nearest-Git-root discovery, including `.git` directories and worktree files.
- Root-to-cwd loading of `AGENTS.md` only.
- Source labels and a shared 32 KiB project-instruction content budget.
- UTF-8 replacement decoding, visible truncation, empty-file skipping, and
  explicit non-`NotFound` read errors.
- Project instructions injected as synthetic contextual user input without
  entering conversation history.
- Stable instruction ordering with todos and recovery overlays rendered
  dynamically for every model step.
- Deterministic discovery, assembly, lifecycle, rollback, and integration tests.
- A paired six-fixture context-assembly capability evaluation.

### Excluded Scope

- Automatic compaction, summarization, token-window monitoring, or long-term
  memory.
- Global user instructions, `AGENTS.override.md`, fallback filenames,
  `CLAUDE.md`, includes, conditional rules, or dynamic child-directory loading.
- Automatic README, Git status, recent-commit, or arbitrary file injection.
- Skills, plugins, MCP, multi-workspace context, configurable prompts, provider
  abstraction, or persistent sessions.

### Completion Criteria

- `SessionContext.capture(cwd)` produces one immutable session snapshot.
- Project root discovery stops at the nearest `.git` marker and never loads
  instructions outside that boundary.
- Multiple `AGENTS.md` files are source-labeled and ordered root to cwd within
  a 32 KiB shared content budget.
- Every provider request contains the same cached project context plus current
  todo/recovery guidance, without mutating or growing conversation history.
- Existing Version 02 todo, rollback, parser, provider, and tool behavior
  remains covered and passing.
- Unit tests, Ruff lint, and Ruff formatting checks pass.
- The paired capability slice records 6/6 process injection and at least 5/6
  Version 03 outcomes, above the Version 02 baseline.
- The Verified × 10 score is recorded as a secondary regression check; any
  result below 5/10 is investigated before completion.

### Verification

- Deterministic suite: **68 passed**.
- Ruff lint and formatting checks: passed.
- Paired capability slice: Version 02 outcome **4/6**; Version 03 process
  **6/6** and outcome **6/6**.
- Official SWE-bench Verified × 10: **7/10 resolved**, 10/10 completed,
  0 empty patches, and 0 harness errors.

## Most Recently Completed Version: 02 — Task Decomposition

Completion status: verified and archived under
`versions/02-task-decomposition/` with tag `version-02-task-decomposition`.

### Goal

Add session-scoped task scheduling so Coding Kid can decompose multi-step work,
track progress with a checklist, and continue from that list — without changing
the Version 01 loop shape.

### Included Scope

- A `todo` tool that replaces the full checklist on each call.
- Todo item fields: `content` and `status` (`pending` / `in_progress` /
  `completed`).
- Validation: at most 20 items of 200 characters each; valid statuses; at most
  one `in_progress`. An empty list clears the checklist.
- Process-local todo state (same lifetime as conversation history).
- Failed or interrupted CLI turns roll todo state back with message history.
- System-prompt guidance to use `todo` on three-or-more-step tasks.
- Inject the current checklist into model instructions when it is non-empty.
- Compact CLI display for todo actions.
- Tests for the tool, agent loop use, and CLI rollback.
- README / architecture / decision updates for the new tool.

### Excluded Scope

- Glob / Grep as first-class tools.
- Plan Mode, plan files, or write-blocking planning phases.
- Disk-persistent or cross-session todos.
- Background tasks, multi-agent workflows, or Task V2-style runtime tasks.
- Prompt-assembly overhaul or context compression beyond injecting the current
  todo list.
- Streaming, MCP, sandbox, approval flow, and TUI work.

### Completion Criteria

- `todo` is registered in `TOOLS` and visible to the model.
- Invalid todo updates return `ERROR:` text the model can recover from.
- Automated tests cover replace behavior, the single `in_progress` rule, loop
  use of `todo`, and CLI rollback of todo state.
- Simple one-step requests can skip `todo`; multi-step guidance is in the system
  prompt.
- Documentation describes the new tool while the implementation stays small and
  readable.
- Version 02 is evaluated on the same SWE-bench Verified × 10 slice used for the
  Version 01 baseline.

### Evaluation Slice

- **Todo evidence (primary):** goal-only multi-step slice under
  `evals/v02-baseline/todo_slice/` (protocol `TODO_SLICE.md`).
  After V01 Outcome filtering: **6** survivors. V02 Process **6/6**, Outcome
  **0/6** (tied with V01) — Todo is used, but wrap-up deliverables still hit the
  tool budget. Scorecard: `todo_slice/SCORECARD.md`.
- **SWE bugfix baseline (not Todo proof):** Verified × 10 under
  `evals/v02-baseline/verified_10_instances.json`.
  Version 01 and cleaned Version 02 both **5 / 10** on the official harness.

## Earlier Completed Version

Version 01 is the minimal complete Coding Kid agent.

Completion status: verified and archived under `versions/01-minimal-agent/`.
The original annotated Git tag is `version-01-minimal-agent`; the final verified
checkpoint is `version-01-minimal-agent-fix2`.

### Goal

Build a small, understandable Python coding agent that accepts terminal input,
calls a model through OpenRouter, executes local tools when requested, feeds tool
results back to the model, and returns a final response to the user.

### Included Scope

- A plain terminal entry point with a process-local conversation history.
- Compact tool activity that hides successful raw results but shows errors.
- Minimal context assembly: system prompt, conversation history, and tool
  definitions.
- A single OpenRouter-backed `provider` that sends a request and returns the raw
  response without streaming.
- Output parsing for assistant text and one or more tool calls.
- Sequential tool execution and continuation of the agent loop.
- Function-based tools registered in a dictionary:
  - Execute a foreground terminal command.
  - Read a text file.
  - Write or create a text file.
  - Search file names and file contents.
  - Apply a text patch.
  - Delete a file.
- Clear comments and tests that make the implementation useful for teaching.

### Excluded Scope

- Task planning, scheduling, todo tools, and multi-agent workflows.
- Persistent conversations, long-term memory, and context compaction.
- Streaming output and parallel tool execution.
- TUI, background tasks, plugins, skills, MCP, and advanced observability.
- Abstraction for additional API providers alongside OpenRouter.
- Sandbox, approval flow, path confinement, and other security boundaries.

### Completion Criteria

- `python -m coding_kid` starts an interactive terminal conversation.
- The agent can complete a model/tool/model loop and return a final answer.
- Tests demonstrate every registered tool, including reading, creating,
  modifying, searching, deleting, patching, and running a command.
- Tests demonstrate parsing multiple tool calls and executing them in order.
- Tests demonstrate the complete agent loop without requiring a live API call.
- The live provider reads its API key from the environment and can be exercised
  manually when credentials and network access are available.
- Setup, run, and test instructions are documented.
- The implementation remains deliberately small and clearly commented.

## Next Action

- Wait for the user to define the next version. Do not define it in advance.

## Version 02 Verification

- Unit suite after todo lifecycle hardening: **52 passed**.
- Ruff lint and formatting checks: passed.
- Hardened live todo smoke: passed on 2026-07-30. The model used and reconciled
  the checklist, created the package and test, and reported `1 passed`.
- First V02 harness score **0 / 10** was invalid (predictions deleted
  `_swe_test.patch`, harness reverse-applied fixes).
- After cleaning predictions: V02 official **5 / 10 resolved** (same count as
  V01; gained pylint, lost astropy). Details in
  `evals/v02-baseline/INVESTIGATION_V02_REGRESSION.md` and
  `evals/v02-baseline/VERIFIED_10_V02_SCORECARD.md`.

## Current Constraints

- Treat `versions/01-minimal-agent/` as a read-only historical checkpoint.
- Treat `versions/02-task-decomposition/` as a read-only historical checkpoint.
- Treat `versions/03-context-assembly/` as a read-only historical checkpoint.
- Treat `versions/04-context-management/` as a read-only historical checkpoint.
- Treat `versions/05-streaming-tui/` as a read-only historical checkpoint.
- Research only as needed to answer a concrete current-version question.
- Do not work on articles unless the user explicitly resumes article work.
- Follow `docs/VERSIONING.md` for routine commits and completed-version
  archives.
- Prefer domestic Docker registry mirrors for SWE-bench harness pulls. Ordinary
  `registry-mirrors` is not enough for cold `sweb.eval.*` images; use explicit
  `docker.1ms.run/...` prefix pulls plus retag (`prepull_swebench_images.py`).
  Keep `--cache_level instance` after a successful pull.
- Do not start a full Verified × 10 harness run until unit tests, live feature
  smoke, Docker mirror smoke, and image pre-pull have passed. See
  `evals/v02-baseline/README.md`.

## Established Project Operations

- `main` holds the continuously evolving implementation.
- Coherent, verified increments receive small local commits.
- A user-declared version completion or transition triggers an archive under
  `versions/` and a matching annotated Git tag.
- The agent performs this local Git maintenance automatically within the limits
  defined in `docs/VERSIONING.md`.

## Available Research

- General research notes: `docs/RESEARCH.md`.
- Claude Code source reports: `docs/reports/claude-code-source-report.md` and its
  Chinese version.
- Codex source reports: `docs/reports/codex-source-report.md` and its Chinese
  version.
- Claude Code and Codex comparison reports under `docs/reports/`.
