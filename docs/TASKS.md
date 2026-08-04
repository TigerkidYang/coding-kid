# Tasks

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
