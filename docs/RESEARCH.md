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
- How to manage background tasks.
- How to implement skills and plugins as pluggable context. (Implemented in
  Version 07.)
- How to implement context auto-compression.
- How to better control the whole loop and workflow.
- How to control the sandbox environment.
- How to design freely configurable MCP support. (Implemented in Version 07.)
- How to initially implement visualization and observability:
  - What should be shown to users.
  - How to design a more suitable terminal UI.

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
