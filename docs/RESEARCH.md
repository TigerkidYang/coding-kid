# Research

Use this file to track source-code reading and comparisons of existing agent
projects.

## Purpose

The user will study strong open-source SWE Agent / Coding Agent projects to
understand their design and implementation details.

Research notes should support two outcomes:

- Better implementation decisions for this repository.
- Better explanations for the teaching article series.

## Research Topic List

### Core Agent Capabilities

- Agent core loop:
  - Task scheduling and task decomposition.
  - Loop and workflow control.
  - Large input prompt assembly.
  - Output parser.
  - Executor.
- Agent tool calling:
  - Terminal command execution.
  - Terminal output reading.
  - Basic file I/O, including read, write, and search.
  - Minimum SWE Agent tool set.

### Advanced Agent Capabilities

- How to implement long-term memory. (Implemented in Version 06.)
- How to implement multi-agent workflows.
- How to manage background tasks. (Implemented in Version 08.)
- How to implement skills and plugins as pluggable context. (Implemented in
  Version 07.)
- How to implement context auto-compression.
- How to better control the whole loop and workflow. (Implemented in Version
  10.)
- How to control the sandbox environment. (Implemented in Version 11.)
- How to design freely configurable MCP support. (Implemented in Version 07.)
- How to initially implement visualization and observability:
  - What should be shown to users.
  - How to design a more suitable terminal UI.

## Supplementary Improvements

### Version 16 Recoverable-Autonomy Source Reading

V16 follows the existing loop/workflow-control and minimum SWE tool-set topics.
It uses Codex and Claude Code only as design evidence; neither source tree is a
runtime dependency.

- Codex official source at local commit `bdd282f`, with the benchmark-era
  `44918ea` submission reference, separates application sandbox/approval from an
  explicit `dangerously-bypass-approvals-and-sandbox` mode intended solely for
  external isolation. Its patch grammar and unified diff machinery demonstrate
  efficient model-visible multi-file changes and bounded review evidence.
- The Claude Code source archive at `a371abb` is an unofficial public sourcemap
  reconstruction, not authoritative Anthropic source. Its built-in file-edit
  history protects directly edited target files, while arbitrary Bash effects
  are not claimed as completely reversible. Its todo guidance informs work but
  does not gate query completion.

Coding Kid combines those general boundaries: required/full for conservative
local work, best-effort/scoped preimages for predictable direct edits, and off
only under explicit unrestricted selection. It deliberately keeps the simpler
`execute + task` teaching split, JSON function tools, fixed loop limits, and no
model- or benchmark-specific prompt.

### Version 15 Benchmark-Driven Hardening

Terminal-Bench 2.1 exercised the completed core and advanced capability topics
under minimal Linux environments, bounded container resources, non-Git working
directories, and long remote inference. The resulting maintenance work stays
inside the existing Research Topic List: executor and file-tool robustness,
runtime-aware tool calling, checkpoint portability, and loop/evaluation
recovery. It does not introduce a new research topic or task-specific solver.

- Bound search/read work before content enters the model or exhausts a task
  container.
- Hide unusable tools using workflow, manager, credential, and repository state.
- Preserve guarded side effects when Git is unavailable through a bounded
  filesystem checkpoint fallback.
- Persist evaluation transitions and separate infrastructure retries from
  official ability outcomes.
- Keep long streaming and non-streaming Responses requests alive through the
  Cloudflare execution path.

The final authorized k=1 run completed all 89 tasks with 50 passes, nine
Agent-timeout zeros, 30 other verifier zeros, no exit 137, and no remaining
infrastructure failure. See `docs/reports/terminal-bench-2.1-k1.md`.

These items do not add new research topics or reopen the completed versions.
They record deeper improvements within topics whose first implementations were
intentionally narrower than the mature capabilities found in the two source
snapshots.

- Permission-governed change workflow. (Implemented in Version 12.) This extends both loop/workflow control
  and sandbox control into one coherent user-facing system: automatic approval,
  approval for every sensitive action, and full access should be distinct from
  Plan, Implementation, and Review modes. The sandbox limits what an action can
  affect, approval determines who may authorize it, and the collaboration mode
  determines what kind of work the Agent may attempt; Plan mode is therefore
  not merely a read-only sandbox and also needs structured questions, diffs,
  checkpoints, and controlled transition into implementation or rollback.
- Rich, continuous execution environment. This deepens the existing Executor,
  terminal-command, terminal-output, background-task, and sandbox topics beyond
  one-shot command execution. It should support interactive process sessions
  such as PTY/stdin continuation, project-native tools and dependencies,
  long-running services with readiness evidence, and predictable host/container
  semantics while preserving bounded output, cancellation, and cleanup.
- Isolated multi-Agent development collaboration. (Implemented in Version 14.)
  This extends the existing
  multi-Agent workflow topic beyond parallel children that share one working
  directory. Agents should be able to work in isolated workspaces or worktrees,
  carry an intentional context fork, own independently reviewable diffs or
  commits, and return work through an explicit merge and conflict-resolution
  process governed by the parent Agent.
- Web search and fetch tools. (Implemented in Version 14.) This is a focused
  expansion of Agent tool calling
  and the practical SWE Agent tool set, not a browser-automation or extension-
  marketplace project. Search should discover relevant sources and fetch should
  retrieve bounded, attributable content under the active network policy so the
  Agent can use current external information without requiring a general browser.

## Version 14 Isolated-Collaboration and Web Source Reading

Version 14 compared the local Claude Code and Codex snapshots only where the
two selected topics required concrete implementation decisions.

Claude Code worktree paths studied include `src/tools/EnterWorktreeTool/`,
`src/tools/ExitWorktreeTool/`, and `src/utils/worktree.ts`. Its useful boundary
is the distinction between a stable repository root and an Agent's effective
cwd, plus explicit enter/exit cleanup and failure handling. Coding Kid carries
that boundary into an application-owned manager, but additionally snapshots a
dirty root into a private baseline and separates review, reconcile, integrate,
accept, rollback, and confirmed discard.

Codex multi-Agent and Web paths studied include its spawn context construction,
external-context events, `ext/web-search`, and `core/web_search.rs`. The useful
invariants are bounded, intentional context inheritance; visible provenance for
external material; and a search capability that remains distinct from general
browser automation.

Claude Code's WebSearch/WebFetch implementation reinforces fixed provider
credentials, GET-only retrieval, domain-aware authorization, redirect limits,
bounded output, and untrusted-content labeling. Brave's official Search API
contract fixes the endpoint and `X-Subscription-Token` header and bounds a query
to 400 characters / 50 words.

The resulting Coding Kid invariants are:

- Child writes default to private Git worktrees; shared cwd is an explicit
  compatibility option.
- A context fork contains only a bounded number of user/visible-assistant
  rounds, never tool calls, tool outputs, or hidden reasoning.
- Integration applies only the child delta and enters the existing V12 stage
  checkpoint; root conflicts never trigger an automatic partial merge.
- Search uses only the fixed Brave endpoint. Fetch is GET-only, public-text-only,
  byte/character/redirect bounded, and revalidates every destination.
- Every resolved address must be globally routable, and the socket is pinned to
  a validated address so DNS rebinding cannot redirect the connection inward.
- Web output is explicitly untrusted and carries numbered source URLs for
  citation; no page text can become an instruction by declaration.

## Version 13 Continuous-Execution Source Reading

Version 13 uses the local Claude Code and Codex snapshots to identify the
foundations shared by mature long-running command systems and the point at
which their designs differ.

Claude Code paths studied include `src/tools/BashTool/BashTool.tsx`,
`src/utils/Shell.ts`, `src/utils/ShellCommand.ts`,
`src/tasks/LocalShellTask/`, and `src/utils/task/TaskOutput.ts`. Its public Bash
path has mature foreground-to-background transfer, bounded file-backed output,
notifications, prompt-stall hints, process-tree cleanup, and reconstructed
shell continuity. It does not expose a general public write-stdin/PTY re-entry
contract; the tmux-backed virtual terminal referenced by internal builds is not
part of the available public Bash implementation.

Codex paths studied include `codex-rs/core/src/unified_exec/`,
`codex-rs/core/src/tools/handlers/unified_exec/`, and
`codex-rs/utils/pty/src/`. Its unified manager registers a process before the
initial wait, yields a stable ID, accepts later TTY input, preserves sessions
across turn end/interruption, bounds output with head/tail retention, and uses
Unix PTYs or Windows ConPTY. Its environment abstraction also carries cwd,
shell, sandbox, and remote identity, but process liveness is not application
service readiness.

The implementation invariants carried into Coding Kid are:

- Decouple process lifetime from any one tool call and register ownership
  before waiting.
- Keep cwd, shell, environment, sandbox, approval, and Agent ownership attached
  to the session for its whole lifetime.
- Treat output as a separately bounded incremental stream with durable overflow
  evidence.
- Make Ctrl+C different from termination, and reclaim the complete process tree
  on every terminal path.
- Preserve one permission and sandbox boundary after yielding; continuing input
  cannot become an ungoverned side channel.
- Present one state to the model and user, and require an explicit health check
  before claiming that a service is ready.

Version 13 intentionally does not add automatic dependency installation,
automatic image construction, remote execution, or process reconnection after
application restart.

## Version 12 Permission-Governed Workflow Source Reading

Version 12 uses the local Claude Code and Codex snapshots to separate
collaboration intent, user authorization, and sandbox enforcement.

Claude Code paths studied:

- `research/repos/claude-code/src/utils/permissions/`
- `research/repos/claude-code/src/hooks/toolPermission/`
- `research/repos/claude-code/src/components/permissions/`
- `research/repos/claude-code/src/tools/EnterPlanModeTool/`
- `research/repos/claude-code/src/tools/ExitPlanModeTool/`
- `research/repos/claude-code/src/utils/plans.ts`

Codex paths studied:

- `research/repos/codex/codex-rs/protocol/src/protocol.rs`
- `research/repos/codex/codex-rs/protocol/src/request_permissions.rs`
- `research/repos/codex/codex-rs/core/src/tools/sandboxing.rs`
- `research/repos/codex/codex-rs/core/src/exec_policy.rs`
- `research/repos/codex/codex-rs/collaboration-mode-templates/templates/`
- `research/repos/codex/codex-rs/core/src/session/review.rs`
- `research/repos/codex/codex-rs/tui/src/chatwidget/plan_implementation.rs`

Useful invariants:

- Collaboration mode, approval policy, and sandbox policy answer different
  questions and must remain separate enforcement layers.
- Deny and hard-safety decisions precede cached grants or permissive modes.
- Approval is a cancellable lifecycle boundary before execution, with explicit
  one-shot, session, deny-feedback, and abort outcomes.
- Plan approval is a committed transition into implementation, not a prompt
  suggestion; Review is non-mutating and targets concrete change evidence.
- Headless workers must route approval to an interactive owner or fail closed.
- Persistent checkpoints may support local rollback, but cannot truthfully undo
  ignored artifacts, remote effects, or conflicting concurrent user edits.

## Version 11 Sandbox-Control Source Reading

Version 11 uses the local Claude Code and Codex snapshots to add one explicit,
fail-closed boundary around model-controlled local effects.

Claude Code paths studied:

- `research/repos/claude-code/src/utils/sandbox/sandbox-adapter.ts`
- `research/repos/claude-code/src/tools/BashTool/shouldUseSandbox.ts`
- `research/repos/claude-code/src/tools/BashTool/BashTool.tsx`
- `research/repos/claude-code/src/commands/sandbox-toggle/sandbox-toggle.tsx`
- `research/repos/claude-code/src/components/sandbox/SandboxSettings.tsx`
- `research/repos/claude-code/src/components/permissions/SandboxPermissionRequest.tsx`

Codex paths studied:

- `research/repos/codex/codex-rs/protocol/src/protocol.rs`
- `research/repos/codex/codex-rs/core/src/tools/sandboxing.rs`
- `research/repos/codex/codex-rs/core/src/safety.rs`
- `research/repos/codex/codex-rs/core/src/sandboxing/mod.rs`
- `research/repos/codex/codex-rs/core/src/exec.rs`
- `research/repos/codex/codex-rs/linux-sandbox/README.md`
- `research/repos/codex/codex-rs/core/tests/suite/approvals.rs`
- `research/repos/codex/codex-rs/core/tests/suite/windows_sandbox.rs`

Useful invariants:

- Policy selection, policy enforcement, and UI status are separate concerns;
  confirmation text is not an isolation boundary.
- Restricted execution must fail closed when its platform backend is missing.
- Writable roots require protected metadata subpaths and path normalization;
  lexical prefix checks alone are insufficient around links and missing paths.
- The model must not be able to grant itself network, environment secrets, an
  unsandboxed retry, or a broader per-call policy.
- Foreground, background, and child-Agent execution must share cleanup and
  cancellation semantics, including one terminal outcome and retained output.
- External tools whose effects cannot be enforced by the active backend must be
  withheld rather than advertised as sandboxed.

## Version 10 Loop-Control Source Reading

Version 10 uses the existing local Claude Code and Codex snapshots to turn the
living synchronous loop into an explicit, bounded Turn/Step runtime.

Claude Code paths studied:

- `research/repos/claude-code/src/query.ts`
- `research/repos/claude-code/src/QueryEngine.ts`
- `research/repos/claude-code/src/query/stopHooks.ts`
- `research/repos/claude-code/src/query/tokenBudget.ts`
- `research/repos/claude-code/src/utils/messageQueueManager.ts`
- `research/repos/claude-code/src/services/tools/toolOrchestration.ts`
- `research/repos/claude-code/src/services/api/withRetry.ts`

Codex paths studied:

- `research/repos/codex/codex-rs/core/src/session/turn.rs`
- `research/repos/codex/codex-rs/core/src/session/session.rs`
- `research/repos/codex/codex-rs/core/src/session/input_queue.rs`
- `research/repos/codex/codex-rs/core/src/session/handlers.rs`
- `research/repos/codex/codex-rs/core/src/tools/parallel.rs`
- `research/repos/codex/codex-rs/core/src/responses_retry.rs`

Useful invariants:

- Continue and terminal decisions need typed reasons rather than scattered
  `continue`, `return`, and exception branches.
- User input that arrives during work is bounded pending turn input. Steering
  interrupts the current step, closes its protocol items, then resumes with a
  fresh cancellation boundary.
- A completed tool side effect and its model-visible evidence must share a
  commit boundary; conversation rollback cannot undo external state.
- Cancellation is hierarchical and every started tool receives exactly one
  completed, failed, aborted, or skipped outcome.
- Only explicitly safe tools may overlap. Stateful, mutating, and unknown
  external tools remain serialized behind an exclusive barrier.
- Provider retries, context/output recovery, budgets, stop checks, and stall
  detection need independent limits plus observable transition events.

## Version 09 Multi-Agent Source Reading

Version 09 is based on a focused source pass over both research objects.

Claude Code paths studied:

- `research/repos/claude-code/src/tools/AgentTool/AgentTool.tsx`
- `research/repos/claude-code/src/tools/AgentTool/runAgent.ts`
- `research/repos/claude-code/src/tools/AgentTool/forkSubagent.ts`
- `research/repos/claude-code/src/tools/AgentTool/resumeAgent.ts`
- `research/repos/claude-code/src/tasks/LocalAgentTask/LocalAgentTask.tsx`
- `research/repos/claude-code/src/coordinator/coordinatorMode.ts`

Codex paths studied:

- `research/repos/codex/codex-rs/core/src/agent/control.rs`
- `research/repos/codex/codex-rs/core/src/agent/registry.rs`
- `research/repos/codex/codex-rs/core/src/agent/control/spawn.rs`
- `research/repos/codex/codex-rs/core/src/tools/handlers/multi_agents/`
- `research/repos/codex/codex-rs/core/src/tools/handlers/multi_agents_v2/`
- `research/repos/codex/codex-rs/core/src/context/multi_agent_mode_instructions.rs`

Useful invariants:

- The root session owns one control plane, while every child owns isolated
  conversation, cancellation, progress, and tool state.
- Spawn must return immediately so multiple child runs can overlap; completion
  changes state and emits a bounded notification but does not itself call a
  model.
- Concurrency, retention, prompt/result size, depth, waiting, and shutdown all
  need explicit bounds and race-safe terminal transitions.
- Fresh task prompts avoid copying large or protocol-sensitive parent history;
  a continuation can reuse one child's own context after the parent synthesizes
  its earlier result.
- Tool pools are capability boundaries. Coding Kid children retain ordinary
  file/terminal, Skill, and MCP tools but cannot spawn children or create
  background shell tasks.
- Coding Kid applies a process-local, single-level star topology. Durable child
  threads, worktrees, sandboxes, remote Agents, model overrides, and peer
  messaging remain separate work.

## Version 08 Background-Task Source Reading

Version 08 uses the existing Claude Code and Codex snapshots to add bounded
local background shell tasks while keeping Coding Kid's Agent loop synchronous.

Claude Code paths studied:

- `research/repos/claude-code/src/Task.ts`
- `research/repos/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx`
- `research/repos/claude-code/src/tasks/LocalShellTask/killShellTasks.ts`
- `research/repos/claude-code/src/utils/task/framework.ts`
- `research/repos/claude-code/src/tools/BashTool/BashTool.tsx`
- `research/repos/claude-code/src/tools/TaskOutputTool/TaskOutputTool.tsx`

Codex paths studied:

- `research/repos/codex/codex-rs/core/src/unified_exec/mod.rs`
- `research/repos/codex/codex-rs/core/src/unified_exec/process.rs`
- `research/repos/codex/codex-rs/core/src/unified_exec/process_manager.rs`
- `research/repos/codex/codex-rs/core/src/unified_exec/async_watcher.rs`
- `research/repos/codex/codex-rs/core/src/tools/handlers/unified_exec/`

Useful invariants:

- Backgrounding is an explicit model choice. Process creation alone does not
  prove that a server is ready; readiness needs output evidence or a health
  probe.
- A task handle separates launch from later `poll`, bounded `wait`, and `stop`
  operations. Waiting cancellation must not implicitly kill the task.
- Process state, output collection, completion notification, retention, and
  process-tree cleanup need one owner and atomic terminal transitions.
- Output and event streams must be bounded while the process is running, not
  only truncated after completion.
- Completion may become visible to the UI and the next model step, but it must
  not autonomously create a paid model request.
- Coding Kid applies a process-local subset: no PTY input, automatic
  backgrounding, task persistence, remote jobs, or multi-agent work.
- Real Windows verification exposed two boundary details not visible in the
  high-level task API: strict provider schemas must require every declared
  field, and assigning a running shell to a Job Object leaves a descendant race.
  V08 therefore creates the shell suspended, assigns the kill-on-close Job,
  resumes it, and retains `taskkill /T` as a second termination fence.

## Version 07 Skills, Plugins, and MCP Source Reading

Version 07 was designed from current source snapshots of Claude Code and Codex,
plus the stable Version 2 MCP Python SDK.

Claude Code paths studied:

- `research/repos/claude-code/src/skills/loadSkillsDir.ts`
- `research/repos/claude-code/src/tools/SkillTool/SkillTool.ts`
- `research/repos/claude-code/src/utils/plugins/pluginLoader.ts`
- `research/repos/claude-code/src/utils/plugins/mcpPluginIntegration.ts`
- `research/repos/claude-code/src/services/mcp/client.ts`

Codex paths studied:

- `research/repos/codex/codex-rs/core-skills/src/`
- `research/repos/codex/codex-rs/plugin/src/manifest.rs`
- `research/repos/codex/codex-rs/core-plugins/src/`
- `research/repos/codex/codex-rs/codex-mcp/src/connection_manager.rs`
- `research/repos/codex/codex-rs/rmcp-client/src/`

Useful invariants:

- Keep bounded Skill metadata model-visible and load complete Skill bodies only
  after explicit or model-selected invocation.
- Treat Plugin as an inert package manifest whose Skills and MCP servers retain
  source identity and a collision-resistant namespace.
- Normalize and bound external tool names, descriptions, schemas, results,
  timeouts, failures, and lifecycle before merging them with built-in tools.
- Executable MCP configuration requires explicit user intent; repository Skill
  discovery alone must never start a process.
- Long-lived async MCP connections need a session-owned lifecycle boundary when
  the surrounding Agent loop remains synchronous.

## Version 07 Terminal-Boundary Correction

The post-verification real Skill A/B run exposed a Windows GBK display failure
on `✳`. A focused source pass treated it as a boundary-class defect rather than
patching that character.

Codex paths studied:

- `research/repos/codex/codex-rs/shell-command/src/powershell.rs`
- `research/repos/codex/codex-rs/core/src/exec.rs`
- `research/repos/codex/codex-rs/core/src/unified_exec/process.rs`
- `research/repos/codex/codex-rs/core/src/unified_exec/head_tail_buffer.rs`

Claude Code paths studied:

- `research/repos/claude-code/src/utils/process.ts`
- `research/repos/claude-code/src/utils/ShellCommand.ts`
- `research/repos/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx`
- `research/repos/claude-code/src/tools/BashTool/BashTool.tsx`

Useful invariants:

- Preserve command/output as Unicode or bytes across the process boundary;
  request UTF-8 explicitly on Windows and decode invalid output lossily.
- Bound output while reading it, retaining useful head and tail data, rather
  than buffering an unbounded result and truncating only afterward.
- A timeout or interruption must terminate the process tree, return partial
  evidence, and place a deadline on pipe draining because descendants can
  inherit stdout/stderr handles.
- Foreground Agent commands must be non-interactive unless a separate PTY/input
  protocol exists.
- UI rendering failures such as an incompatible redirected-output codec must
  not roll back an otherwise valid tool/Agent protocol round.

Coding Kid applies the subset appropriate to its foreground-only terminal:
UTF-16LE encoded PowerShell input with explicit UTF-8 output, byte-first
head/tail capture, legacy/lossy decoding fallback, CLIXML normalization,
process-tree cleanup, partial timeout results, closed stdin, and safe CLI
rendering. Background processes, PTY input, and sandboxing remain separate.

## Version 06 Persistent-Memory Source Reading

Version 06 was designed from a fresh source pass over both research objects,
not only the earlier reports.

Claude Code paths studied:

- `research/repos/claude-code/src/services/SessionMemory/`
- `research/repos/claude-code/src/services/extractMemories/extractMemories.ts`
- `research/repos/claude-code/src/services/autoDream/autoDream.ts`
- `research/repos/claude-code/src/memdir/`

Useful invariants:

- Current-session summaries, turn-level durable extraction, and cross-session
  consolidation are separate mechanisms.
- Durable memory is selective and typed; derivable repository facts and
  current-task ephemera should not be stored.
- A bounded index can route to detailed memory without a vector database.
- Extraction cursors advance only on success and consolidation uses an
  exclusive lock with failure rollback.

Codex paths studied:

- `research/repos/codex/codex-rs/memories/README.md`
- `research/repos/codex/codex-rs/memories/write/src/phase1.rs`
- `research/repos/codex/codex-rs/memories/write/src/phase2.rs`
- `research/repos/codex/codex-rs/state/memory_migrations/0001_memories.sql`
- `research/repos/codex/codex-rs/ext/memories/templates/memories/read_path.md`

Useful invariants:

- Raw session/rollout evidence and long-term memory serve different purposes.
- Two-stage extraction and consolidation need source timestamps, leases,
  retries, bounded candidate selection, and success-only promotion.
- Memory provenance and actual-use tracking support retention and verification.
- Memory generation must exclude the current session and prevent recursive
  memory or tool behavior.

Coding Kid applies these ideas with hash-chained JSONL session logs, SQLite
metadata, project-only automatic memory, explicit global user memory, bounded
lexical recall, and machine-readable usage citations. Generic background tasks,
multi-agent infrastructure, and vector retrieval remain separate topics.

## Suggested Note Format

```markdown
## Project name

Repository:
Link or local path.

Why study it:
What this project can teach us.

Key ideas:
- ...

Implementation details:
- ...

Questions:
- ...

Useful takeaways:
- ...
```

## Candidates

## Version 04 Context-Management Source Reading

The Version 04 design was checked against the source snapshots rather than only
the earlier reports.

Claude Code paths:
- `research/repos/claude-code/src/services/compact/autoCompact.ts`
- `research/repos/claude-code/src/services/compact/compact.ts`
- `research/repos/claude-code/src/services/compact/microCompact.ts`
- `research/repos/claude-code/src/services/compact/prompt.ts`
- `research/repos/claude-code/src/query.ts`

Useful invariants:
- Reserve output headroom before the window is full.
- Treat complete model/tool API rounds as the smallest safe split unit.
- Replace working context only after a valid summary exists.
- Preserve structured task state and regenerate canonical attachments after
  compaction instead of relying on summary prose.
- Bound reactive retries and stop repeated failed automatic compactions.

Codex paths:
- `research/repos/codex/codex-rs/core/src/session/context_window.rs`
- `research/repos/codex/codex-rs/core/src/session/turn.rs`
- `research/repos/codex/codex-rs/core/src/compact.rs`
- `research/repos/codex/codex-rs/core/src/compact_remote_v2.rs`
- `research/repos/codex/codex-rs/prompts/templates/compact/prompt.md`

Useful invariants:
- Model-window accounting is separate from the compaction implementation.
- Compaction may happen before a turn or inside a continuing tool turn.
- Recent real user intent is retained alongside a handoff summary.
- Canonical session context is re-injected after the history transition.
- Compaction is an observable lifecycle event, not an incidental list rewrite.

### First Parallel Study Set

Reports:
- `docs/reports/claude-code-source-report.md`
- `docs/reports/claude-code-source-report-zh.md`
- `docs/reports/codex-source-report.md`
- `docs/reports/codex-source-report-zh.md`
- `docs/reports/claude-code-vs-codex-comparison.md`
- `docs/reports/claude-code-vs-codex-comparison-zh.md`

## Claude Code source archive

Repository:
https://github.com/yasasbanukaofficial/claude-code

Local path:
`research/repos/claude-code`

Snapshot:
- Stars checked on 2026-06-29: 3612.
- Default branch: `main`.
- Local HEAD: `a371abb`.

Why study it:
Use this repository to study Claude Code's extracted implementation shape and
compare it with Codex. Focus especially on agent loop, tool calling, prompt
assembly, permission flow, and terminal/file interaction.

Questions:
- How is the main loop organized?
- How are tools represented and dispatched?
- How is context assembled and compressed?
- How are terminal commands and file edits handled?
- Which parts are product workflow, and which parts are core agent mechanics?

Initial assessment:
- The author's README says the repository is a backup of source recovered from
  an npm sourcemap, not an official Anthropic repository.
- The author says they did not leak the files and collected public findings for
  research/archival use.
- The root only contains `README.md`, `assets/`, and `src/`; there is no
  `package.json` or `tsconfig.json`, so this should be treated as a source
  archive rather than a directly runnable project.
- The `src/` tree is substantial: 1902 source files, about 30.9 MB, mostly
  TypeScript and TSX.
- The source tree contains plausible implementations for the README's major
  claims: `main.tsx`, `QueryEngine.ts`, `Tool.ts`, `tools/`, `services/`,
  `coordinator/`, `buddy/`, `services/autoDream/`, `utils/undercover.ts`, and
  feature gates such as `KAIROS`, `ULTRAPLAN`, and `COORDINATOR_MODE`.
- This source archive looks useful for architecture study, but it should not be
  treated as a clean, buildable upstream dependency.

Good first files to read:
- `src/query.ts`: async generator core loop and model/tool-message flow.
- `src/QueryEngine.ts`: high-level query orchestration and app state wiring.
- `src/Tool.ts`: tool abstraction, permission context, and `buildTool`.
- `src/tools.ts`: built-in tool registration and tool-set selection.
- `src/tools/BashTool/BashTool.tsx`: terminal execution, permissions, sandbox,
  and background execution behavior.
- `src/tools/FileReadTool/FileReadTool.ts`: file read behavior and limits.
- `src/tools/FileEditTool/FileEditTool.ts`: edit workflow and validation.
- `src/services/autoDream/`: long-term memory consolidation.
- `src/services/compact/`: context compaction.
- `src/tools/AgentTool/`: subagent/multi-agent mechanics.
- `src/services/mcp/`: MCP connection and tool/resource integration.

## OpenAI Codex

Repository:
https://github.com/openai/codex

Local path:
`research/repos/codex`

Snapshot:
- Stars checked on 2026-06-29: 94189.
- Default branch: `main`.
- Local HEAD: `bdd282f`.

Why study it:
Use Codex as the main open-source reference for a modern terminal coding agent.
Focus on architecture, sandboxing, approval flow, tool execution, patch/edit
workflow, CLI design, and how the agent turns user intent into repository
changes.

Questions:
- Where is the core agent loop implemented?
- How are model calls, tools, approvals, and sandboxing connected?
- How does Codex represent file edits and patches?
- How does Codex keep terminal UI, task state, and execution state synchronized?
- Which architectural ideas should be adapted into the Python implementation?
