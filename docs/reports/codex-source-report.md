# OpenAI Codex Source Research Report

Date: 2026-06-29

Local source: `research/repos/codex`

## Assessment

OpenAI Codex is highly useful for this project as a production-grade
architecture reference. It is not a direct Python blueprint, but the Rust
workspace under `codex-rs/` shows a modern terminal coding agent organized
around threads, sessions, turns, streaming model responses, tool dispatch,
approval/sandbox policy, context compaction, and event-driven UI.

The most relevant area is `codex-rs/core`, with supporting crates for
sandboxing, protocol, TUI, plugins, skills, MCP, file systems, and cloud tasks.

## Core Agent Loop

Key files:

- `codex-rs/core/src/session/turn.rs`
- `codex-rs/core/src/session/handlers.rs`
- `codex-rs/core/src/session/session.rs`
- `codex-rs/core/src/session/input_queue.rs`
- `codex-rs/core/src/client.rs`
- `codex-rs/core/src/stream_events_utils.rs`

Observed structure:

- `run_turn` is the central loop.
- It prepares context, injects skills/plugins, records input, builds
  model-visible history, streams Responses API events, executes tool calls,
  appends tool outputs, and loops until no follow-up is needed.
- `try_run_sampling_request` parses streaming response events: output item
  lifecycle, text deltas, reasoning deltas, tool-call deltas,
  `response.completed`, token usage, and turn diff emission.
- `build_prompt` builds the model request with input, base instructions, tools,
  context, final output schema, and metadata.
- `Session` keeps active turn state, input queue, services, config, telemetry,
  permission profile, and environment selection.
- `ModelClient` is session-scoped while `ModelClientSession` is turn-scoped.

Core shape:

`Thread -> Session -> Turn -> Step`, with explicit context snapshots and a loop
of sample -> parse -> execute tools -> append outputs -> resample.

## Tool Calling

Key files:

- `codex-rs/core/src/tools/router.rs`
- `codex-rs/core/src/tools/registry.rs`
- `codex-rs/core/src/tools/parallel.rs`
- `codex-rs/core/src/tools/spec_plan.rs`
- `codex-rs/core/src/tools/handlers/shell.rs`
- `codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`
- `codex-rs/core/src/tools/handlers/apply_patch.rs`
- `codex-rs/core/src/exec.rs`
- `codex-rs/file-system/src/lib.rs`

Observed structure:

- `ToolRouter` parses model tool calls and dispatches through `ToolRegistry`.
- `CoreToolRuntime` defines a local tool contract with spec, execution, hooks,
  telemetry, search metadata, and argument diff consumers.
- `ToolCallRuntime` schedules tool calls, supports parallel-capable tools,
  cancellation, abort responses, and serialized execution for unsafe tools.
- `spec_plan.rs` builds the model-visible tool list from core tools, MCP tools,
  dynamic tools, extension tools, deferred tools, hosted web/image tools, and
  multi-agent tools.
- Shell execution has both legacy and newer unified exec handlers.
- `exec_command` supports process IDs, TTY, stdin continuation, yield time,
  output-token caps, remote environments, sandbox permissions, approval flow,
  and apply-patch interception.
- `apply_patch.rs` parses freeform patches, emits patch progress, computes
  write permissions, and applies changes through the active environment file
  system.
- `ExecutorFileSystem` abstracts local/remote file operations.

Minimum SWE agent tool set suggested by Codex:

- Terminal command execution.
- Terminal output capture and truncation.
- Patch application.
- File access through shell and environment filesystem abstractions.
- Search via shell tools such as `rg`, plus deferred tool discovery.
- Approval/permission flow.
- MCP tools/resources.

Codex does not appear to rely primarily on simple model-visible `read_file` and
`write_file` tools. It leans on shell, patch, MCP, and environment filesystem
abstractions.

## Advanced Capabilities

### Long-Term Memory

Key files:

- `codex-rs/core/src/client.rs`
- `codex-rs/codex-api/src/endpoint/memories.rs`
- `codex-rs/core/src/stream_events_utils.rs`
- `codex-rs/memories/`

Observed structure:

- `client.rs` exposes `summarize_memories`.
- The API endpoint calls `/memories/trace_summarize`.
- Stream handling detects memory citations and records usage.
- The `codex-rs/memories/` crate needs a separate deep pass.

### Multi-Agent Workflows

Key files:

- `codex-rs/core/src/agent/control.rs`
- `codex-rs/core/src/tools/handlers/multi_agents.rs`
- `codex-rs/core/src/tools/handlers/multi_agents_v2.rs`
- `codex-rs/core/src/thread_manager.rs`

Observed structure:

- Agent control manages spawning, sending, waiting, and resuming agents.
- Multi-agent tools expose subagent operations to the model/tool layer.
- `thread_manager.rs` owns thread creation, forking, resume, and active thread
  registry.

### Background Tasks

Key files:

- `codex-rs/cloud-tasks/src/app.rs`
- `codex-rs/core/src/tasks/`

Observed structure:

- Cloud tasks have a separate TUI/app for task lists, diffs, apply flow, and
  background enrichment.
- Core tasks include regular, compact, review, and user shell command machinery.

### Skills And Plugins

Key files:

- `codex-rs/core/src/skills.rs`
- `codex-rs/core-skills/src/service.rs`
- `codex-rs/core/src/plugins/mod.rs`
- `codex-rs/core-plugins/src/manager.rs`

Observed structure:

- Skills are loaded and injected into context.
- Skill snapshots are cached by cwd/config.
- Plugins can contribute skills, hooks, apps, MCP servers, and marketplace
  metadata.

### Context Compression

Key files:

- `codex-rs/core/src/compact.rs`
- `codex-rs/core/src/session/context_window.rs`
- `codex-rs/core/src/session/turn.rs`

Observed structure:

- `compact.rs` implements manual and auto compaction.
- `context_window.rs` computes token status.
- `run_turn` can trigger compaction mid-turn when token limits or new context
  window requests require it.

### Sandbox

Key files:

- `codex-rs/core/src/sandboxing/mod.rs`
- `codex-rs/sandboxing/src/lib.rs`
- `codex-rs/sandboxing/src/manager.rs`
- `codex-rs/sandboxing/src/seatbelt.rs`
- `codex-rs/sandboxing/src/bwrap.rs`
- `codex-rs/sandboxing/src/landlock.rs`
- `codex-rs/sandboxing/src/windows.rs`

Observed structure:

- Core sandboxing adapts exec requests to sandbox execution.
- Platform-specific implementations cover macOS Seatbelt, Linux bwrap/Landlock,
  and Windows sandbox behavior.

### MCP

Key files:

- `codex-rs/core/src/mcp.rs`
- `codex-rs/core/src/session/mcp.rs`
- `codex-rs/core/src/tools/handlers/mcp.rs`

Observed structure:

- MCP config merges user config, plugin registrations, app compatibility
  servers, and extension overlays.
- Runtime projection decides which MCP servers/tools are available to a turn.
- MCP tools are adapted into model-visible tool specs and execution handlers.

### Terminal UI And Observability

Key files:

- `codex-rs/tui/src/app.rs`
- `codex-rs/tui/src/chatwidget.rs`
- `codex-rs/otel/`

Observed structure:

- The TUI consumes protocol events and renders committed transcript cells plus
  active streaming cells.
- App state wires session events, approvals, plugins, skills, settings, and
  thread UI state.
- Telemetry and OpenTelemetry crates support production observability.

## Most Important Files For Deep Reading

1. `codex-rs/core/src/session/turn.rs`
2. `codex-rs/core/src/session/session.rs`
3. `codex-rs/core/src/session/handlers.rs`
4. `codex-rs/core/src/session/input_queue.rs`
5. `codex-rs/core/src/stream_events_utils.rs`
6. `codex-rs/core/src/client.rs`
7. `codex-rs/core/src/tools/spec_plan.rs`
8. `codex-rs/core/src/tools/router.rs`
9. `codex-rs/core/src/tools/registry.rs`
10. `codex-rs/core/src/tools/parallel.rs`
11. `codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`
12. `codex-rs/core/src/tools/handlers/apply_patch.rs`
13. `codex-rs/core/src/compact.rs`
14. `codex-rs/core/src/thread_manager.rs`
15. `codex-rs/tui/src/chatwidget.rs`

## Gaps And Uncertainties

- Memory generation/consolidation under `codex-rs/memories/` needs a separate
  pass.
- The sandbox layer was sampled but not deeply read for each platform.
- Multi-agent routing/control was confirmed, but agent graph persistence still
  needs reading under `codex-rs/agent-graph-store`.
- UI/event design should pair `codex-rs/app-server-protocol` with
  `codex-rs/tui/src/app/app_server_events.rs`.

