# Claude Code Source Archive Research Report

Date: 2026-06-29

Local source: `research/repos/claude-code`

## Assessment

This archive looks coherent and useful for technical research, but not directly
buildable. It has a large TypeScript/TSX source tree under `src/`, with
recognizable subsystems for query orchestration, tools, MCP, memory, subagents,
background tasks, sandboxing, and terminal UI.

The root lacks `package.json` and `tsconfig.json`, so treat it as a recovered
source archive for reading rather than as an upstream dependency.

## Core Agent Loop

Key files:

- `src/query.ts`
- `src/QueryEngine.ts`
- `src/services/api/claude.ts`
- `src/utils/messages.ts`
- `src/utils/queryContext.ts`
- `src/constants/prompts.ts`
- `src/context.ts`

Observed structure:

- `query()` delegates to `queryLoop()` as the main async-generator loop.
- The loop streams model output, detects `tool_use` blocks, executes tools,
  appends tool results, and continues until a terminal condition.
- The loop also handles fallback model retry, aborts, max-turns, token budget,
  tool-result budget, compaction, and stop hooks.
- `QueryEngine.ts` wraps the lower-level loop with conversation/session state:
  mutable messages, read-file cache, permission denials, usage, transcript
  persistence, system prompt assembly, skills/plugins loading, and SDK message
  normalization.
- Prompt assembly combines default system prompt, tool-aware prompt sections,
  git status, date, CLAUDE.md-style context, MCP instructions, output styles,
  and custom append prompts.

Core shape:

`Engine.submitMessage()` -> process user input and context -> `query()` loop ->
stream model -> detect tool calls -> execute tools -> append tool results ->
continue.

## Tool Calling

Key files:

- `src/Tool.ts`
- `src/tools.ts`
- `src/services/tools/toolExecution.ts`
- `src/services/tools/toolOrchestration.ts`
- `src/services/tools/StreamingToolExecutor.ts`
- `src/tools/BashTool/BashTool.tsx`
- `src/utils/Shell.ts`
- `src/tools/FileReadTool/FileReadTool.ts`
- `src/tools/FileEditTool/FileEditTool.ts`
- `src/tools/FileWriteTool/FileWriteTool.ts`
- `src/tools/GlobTool/GlobTool.ts`
- `src/tools/GrepTool/GrepTool.ts`

Observed structure:

- `Tool.ts` defines the central tool abstraction: name, input schema, call,
  prompt, permission checks, validation, read-only status, concurrency safety,
  result size, MCP flag, and UI render hooks.
- `tools.ts` assembles the built-in tool pool.
- `toolExecution.ts` dispatches a single tool call: schema validation,
  pre-tool hooks, permission resolution, tool execution, progress, and error
  conversion into tool-result messages.
- `toolOrchestration.ts` batches tool calls and runs safe/read-only tools in
  parallel while serializing unsafe tools.
- `StreamingToolExecutor.ts` can start tools while tool-use blocks are still
  streaming, then buffer ordered results.
- `BashTool` supports timeout, streaming progress, background execution,
  persisted large output, sandbox wrapping, CWD recovery, image output, command
  semantics, and stdout/stderr handling.
- File edit/write tools require prior reads and reject stale writes when the
  file changed.

Minimum SWE agent tool set suggested by this archive:

- Bash / terminal execution.
- File read.
- File edit.
- File write.
- Glob.
- Grep.
- Todo or planning tool.
- Task output/background task reading.

## Advanced Capabilities

### Long-Term Memory

Key files:

- `src/memdir/memdir.ts`
- `src/context.ts`
- `src/services/autoDream/autoDream.ts`

Observed structure:

- File-based memory uses `MEMORY.md`-style prompt mechanics.
- `context.ts` loads CLAUDE.md-style files into user context.
- `autoDream.ts` runs background memory consolidation as a forked agent after
  time/session gates.

### Multi-Agent Workflows

Key files:

- `src/tools/AgentTool/AgentTool.tsx`
- `src/tools/AgentTool/runAgent.ts`
- `src/tools/AgentTool/forkSubagent.ts`

Observed structure:

- `AgentTool` launches sync/async agents, teammates, remote agents,
  worktree-isolated agents, and fork subagents.
- `runAgent.ts` builds subagent context, tool pool, permissions, transcripts,
  MCP, hooks, and calls `query()`.
- Forked workers can inherit parent context/system prompt, which appears useful
  for prompt-cache sharing.

### Background Tasks

Key files:

- `src/tasks/LocalShellTask/LocalShellTask.tsx`
- `src/tasks/LocalAgentTask/LocalAgentTask.tsx`
- `src/tasks/RemoteAgentTask/RemoteAgentTask.tsx`
- `src/tools/TaskOutputTool/TaskOutputTool.tsx`

Observed structure:

- Shell tasks and agent tasks have explicit lifecycle objects.
- Background commands can emit task notifications and write output to files.
- `TaskOutputTool` can poll task state, though newer flows may prefer reading
  output files directly.

### Skills And Plugins

Key files:

- `src/skills/loadSkillsDir.ts`
- `src/tools/SkillTool/SkillTool.tsx`
- `src/utils/plugins/pluginLoader.ts`

Observed structure:

- Skills are loaded from `SKILL.md` frontmatter with path triggers, allowed
  tools, hooks, shell blocks, and arguments.
- Plugins can provide commands, agents, hooks, and marketplace/session cached
  behavior.

### Context Compression

Key files:

- `src/services/compact/autoCompact.ts`
- `src/services/compact/compact.ts`
- `src/services/compact/microCompact.ts`
- `src/services/compact/sessionMemoryCompact.ts`
- `src/query.ts`

Observed structure:

- The query loop wires snip, microcompact, context collapse, autocompact, and
  reactive recovery into execution.
- `autoCompact.ts` decides when to compact and chooses compaction path.

### Sandbox

Key files:

- `src/utils/sandbox/sandbox-adapter.ts`
- `src/tools/BashTool/shouldUseSandbox.ts`

Observed structure:

- Sandbox config is derived from settings/permissions.
- It covers filesystem allow/deny rules, network domains, dangerous settings
  paths, git worktree handling, and dependency checks.

### MCP

Key files:

- `src/services/mcp/config.ts`
- `src/services/mcp/client.ts`
- `src/tools/MCPTool/MCPTool.ts`

Observed structure:

- MCP config merges global, project, managed, and plugin server configs.
- Client supports stdio, SSE, HTTP, WebSocket, and SDK transports.
- MCP tools are wrapped into the same `Tool` abstraction.

### Terminal UI And Observability

Key files:

- `src/components/App.tsx`
- `src/screens/REPL.tsx`
- `src/components/ContextVisualization.tsx`
- `src/utils/telemetry/sessionTracing.ts`
- `src/utils/telemetry/perfettoTracing.ts`
- `src/utils/queryProfiler.ts`
- `src/utils/headlessProfiler.ts`

Observed structure:

- The UI is an Ink/React terminal application.
- `ContextVisualization.tsx` renders token/context usage, memory files, MCP
  tools, skills, agents, and collapse state.
- There are tracing/profiling hooks for session and query execution.

## Most Important Files For Deep Reading

1. `src/query.ts`
2. `src/QueryEngine.ts`
3. `src/Tool.ts`
4. `src/tools.ts`
5. `src/services/tools/toolExecution.ts`
6. `src/services/tools/toolOrchestration.ts`
7. `src/services/api/claude.ts`
8. `src/tools/BashTool/BashTool.tsx`
9. `src/tools/FileReadTool/FileReadTool.ts`
10. `src/tools/FileEditTool/FileEditTool.ts`
11. `src/tools/AgentTool/AgentTool.tsx`
12. `src/tools/AgentTool/runAgent.ts`
13. `src/services/compact/autoCompact.ts`
14. `src/services/mcp/client.ts`
15. `src/skills/loadSkillsDir.ts`

## Gaps And Uncertainties

- The archive cannot be compiled as-is because root build metadata is missing.
- Many modules are feature-gated, so active shipped paths are unclear.
- Some TSX files appear transformed or compiler-output-like.
- MCP, plugins, sandbox runtime, telemetry, and model API behavior depend on
  external packages/services not included in the archive.
- Deeper reading is needed for compaction internals, MCP tool wrapping,
  permission resolution, hook execution, and the Ink rendering pipeline.

