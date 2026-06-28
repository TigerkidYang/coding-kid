# Claude Code Source Archive vs OpenAI Codex

Date: 2026-06-29

Sources:

- Claude Code source archive: `research/repos/claude-code`
- OpenAI Codex: `research/repos/codex`

## High-Level Comparison

Claude Code and Codex are both valuable, but they should serve different roles
in this project.

Claude Code is better for studying product mechanics and feature breadth. Its
source archive exposes many concrete TypeScript/TSX modules for tools, memory,
subagents, background tasks, skills/plugins, MCP, compaction, sandboxing, and
Ink terminal UI. It is not directly buildable from the archive.

Codex is better for studying engineering architecture. Its official repository
has a large Rust workspace with clear crates for core session logic, tool
runtime, sandboxing, TUI, plugins, skills, MCP, thread management, and protocol
events. It is a stronger reference for production structure.

## Core Loop

Claude Code:

- Main loop lives in `src/query.ts`.
- High-level orchestration lives in `src/QueryEngine.ts`.
- Shape: engine submits message -> assemble context -> stream model -> detect
  tool calls -> execute tools -> append results -> continue.
- The loop is an async generator and integrates compaction, fallback, stop hooks,
  aborts, token budgets, and tool-result budgets.

Codex:

- Main loop lives in `codex-rs/core/src/session/turn.rs`.
- Session handling lives in `codex-rs/core/src/session/session.rs` and
  `handlers.rs`.
- Shape: thread/session/turn -> build prompt -> stream Responses API events ->
  parse output items -> execute tools -> append outputs -> continue.
- It has a stronger separation between thread, session, turn, input queue, model
  client, and UI protocol events.

Project takeaway:

Use Claude Code to understand a compact async-loop shape for a Python MVP. Use
Codex to design the longer-term architecture around thread/session/turn/event
boundaries.

## Tool Calling

Claude Code:

- Central abstraction: `src/Tool.ts`.
- Registry: `src/tools.ts`.
- Execution: `src/services/tools/toolExecution.ts`.
- Orchestration: `src/services/tools/toolOrchestration.ts`.
- Streaming execution: `src/services/tools/StreamingToolExecutor.ts`.
- Has explicit model-visible file tools: Read, Edit, Write, Glob, Grep.

Codex:

- Router: `codex-rs/core/src/tools/router.rs`.
- Registry: `codex-rs/core/src/tools/registry.rs`.
- Parallel runtime: `codex-rs/core/src/tools/parallel.rs`.
- Tool plan/spec builder: `codex-rs/core/src/tools/spec_plan.rs`.
- Terminal execution: `unified_exec/exec_command.rs`.
- Patch editing: `apply_patch.rs`.
- File system abstraction: `codex-rs/file-system/src/lib.rs`.

Project takeaway:

For a Python MVP, Claude Code's explicit `Tool` abstraction and file tools are
easier to imitate. For a mature version, Codex's registry/router/runtime split
is cleaner and more scalable.

## Terminal And File Operations

Claude Code:

- `BashTool` is rich and product-focused: command semantics, sandbox decisions,
  backgrounding, large output persistence, image output, stdout/stderr handling,
  and progress UI.
- File tools require prior reads and defend against stale writes.
- Grep/Glob are first-class tools.

Codex:

- Terminal execution is integrated with approvals, sandbox permissions, remote
  environments, TTY/stdin continuation, process IDs, and output token caps.
- File edits are primarily patch-oriented.
- File access is abstracted through local/remote environment file systems.

Project takeaway:

Start with Claude Code's simple model-visible Bash/Read/Edit/Write/Grep/Glob
tool set. Later, borrow Codex's patch-first editing and environment filesystem
abstractions.

## Long-Term Memory

Claude Code:

- Clear file-based memory story: `src/memdir/memdir.ts`, `src/context.ts`,
  `src/services/autoDream/autoDream.ts`.
- `autoDream` is especially relevant: background consolidation after time/session
  gates.

Codex:

- Memory exists but needs deeper reading.
- Confirmed points include `summarize_memories`, `/memories/trace_summarize`,
  memory citations, and `codex-rs/memories/`.

Project takeaway:

Claude Code is the better first reference for long-term memory. Its file-based
memory and auto-consolidation fit this project's current AGENTS/docs memory
strategy.

## Multi-Agent And Background Work

Claude Code:

- `AgentTool` launches sync/async agents, fork subagents, remote agents, and
  worktree-isolated agents.
- Background shell and agent tasks have explicit task objects.

Codex:

- Multi-agent control is tied to thread management and tool handlers.
- `thread_manager.rs` and `agent/control.rs` are important architecture
  references.
- Cloud tasks show a separate product surface for background work.

Project takeaway:

Claude Code is easier for studying how subagents feel as user-facing tools.
Codex is better for durable thread/task architecture.

## Skills, Plugins, And MCP

Claude Code:

- Skills are loaded from `SKILL.md` frontmatter and can include path triggers,
  allowed tools, hooks, shell blocks, and arguments.
- Plugins can add commands, agents, hooks, and marketplace/session behavior.
- MCP config merges global/project/managed/plugin sources and wraps MCP tools
  into the same `Tool` abstraction.

Codex:

- Skills and plugins are split into dedicated crates/services.
- Plugins can contribute skills, hooks, apps, MCP servers, and marketplace
  metadata.
- MCP is projected into turns through config/session/tool-handler layers.

Project takeaway:

For Python, start with Claude Code's simpler skill/plugin loading model. Later,
Codex's crate/service separation suggests how to keep plugin systems from
polluting the core loop.

## Context Compression

Claude Code:

- Multiple compaction strategies are wired directly into `query.ts`: snip,
  microcompact, context collapse, autocompact, and recovery.

Codex:

- `compact.rs` and `context_window.rs` provide a cleaner architectural surface.
- `run_turn` triggers compaction when token limits or context-window requests
  require it.

Project takeaway:

Claude Code is useful for seeing all the real product cases. Codex is better for
designing clean boundaries.

## Sandbox

Claude Code:

- Sandbox decisions sit near Bash execution and convert settings/permissions
  into runtime config.

Codex:

- Sandbox is a first-class cross-platform subsystem with macOS, Linux, and
  Windows implementations.

Project takeaway:

For MVP, implement simple permission and workspace-boundary checks. For mature
versions, Codex is the stronger sandbox reference.

## Terminal UI And Observability

Claude Code:

- Ink/React terminal UI.
- `ContextVisualization.tsx` is directly relevant to showing users context,
  memory, MCP tools, skills, agents, and collapse state.
- Tracing/profiling utilities exist in the source archive.

Codex:

- Rust TUI with protocol-event-driven rendering.
- `chatwidget.rs` consumes session events and renders committed/active cells.
- OpenTelemetry support is integrated.

Project takeaway:

Claude Code is better for designing user-facing terminal affordances. Codex is
better for event-driven UI architecture.

## Recommended Study Order

1. Claude Code `src/query.ts` and Codex `codex-rs/core/src/session/turn.rs`
   side by side.
2. Claude Code `Tool.ts`/`toolExecution.ts` and Codex
   `tools/registry.rs`/`tools/router.rs`.
3. Claude Code `BashTool` and Codex `unified_exec/exec_command.rs`.
4. Claude Code file tools and Codex `apply_patch.rs`.
5. Claude Code `autoDream` and Codex `memories/`.
6. Claude Code `AgentTool` and Codex `agent/control.rs` plus
   `thread_manager.rs`.
7. Claude Code `ContextVisualization.tsx` and Codex `tui/src/chatwidget.rs`.

## Design Guidance For Our Python Agent

MVP:

- Use a simple async loop inspired by Claude Code.
- Implement explicit tools: Bash, Read, Write, Edit, Glob, Grep, Todo.
- Use repository files for durable memory.
- Keep permissions simple but visible.
- Store all state in plain objects/files before introducing services.

Next stage:

- Introduce Codex-like boundaries: Thread, Session, Turn, ToolRegistry,
  ToolRuntime, EventBus.
- Add patch-first editing.
- Add context-window accounting and compaction.
- Add background tasks and subagents.

Mature stage:

- Add sandbox profiles.
- Add plugin/skill/MCP registration.
- Add event-driven terminal UI.
- Add observability and trace logs.
- Add memory consolidation similar to Claude Code's autoDream, but with our own
  repository documentation strategy.

