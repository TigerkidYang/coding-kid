# OpenAI Codex 源码研究报告

日期：2026-06-29

本地源码：`research/repos/codex`

## 总体判断

OpenAI Codex 对这个项目非常有参考价值，尤其适合作为生产级架构参考。它不是 Python 的直接蓝图，但 `codex-rs/` 下的 Rust workspace 展示了一个现代 terminal coding agent 如何围绕 threads、sessions、turns、流式模型响应、工具分发、approval/sandbox policy、context compaction、事件驱动 UI 来组织。

最相关的部分是 `codex-rs/core`，周边还有 sandboxing、protocol、TUI、plugins、skills、MCP、file systems、cloud tasks 等 crate。

## 核心 Agent Loop

关键文件：

- `codex-rs/core/src/session/turn.rs`
- `codex-rs/core/src/session/handlers.rs`
- `codex-rs/core/src/session/session.rs`
- `codex-rs/core/src/session/input_queue.rs`
- `codex-rs/core/src/client.rs`
- `codex-rs/core/src/stream_events_utils.rs`

观察到的结构：

- `run_turn` 是中央 loop。
- 它准备上下文、注入 skills/plugins、记录输入、构建模型可见历史、流式读取 Responses API events、执行工具调用、追加工具输出，并循环直到不需要继续。
- `try_run_sampling_request` 解析流式响应事件：output item lifecycle、text deltas、reasoning deltas、tool-call deltas、`response.completed`、token usage、turn diff emission。
- `build_prompt` 构建模型请求，包括 input、base instructions、tools、context、final output schema、metadata。
- `Session` 保存 active turn state、input queue、services、config、telemetry、permission profile、environment selection。
- `ModelClient` 是 session-scoped，`ModelClientSession` 是 turn-scoped。

核心形状：

`Thread -> Session -> Turn -> Step`，并且显式保存 context snapshot，loop 是 sample -> parse -> execute tools -> append outputs -> resample。

## Tool Calling

关键文件：

- `codex-rs/core/src/tools/router.rs`
- `codex-rs/core/src/tools/registry.rs`
- `codex-rs/core/src/tools/parallel.rs`
- `codex-rs/core/src/tools/spec_plan.rs`
- `codex-rs/core/src/tools/handlers/shell.rs`
- `codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`
- `codex-rs/core/src/tools/handlers/apply_patch.rs`
- `codex-rs/core/src/exec.rs`
- `codex-rs/file-system/src/lib.rs`

观察到的结构：

- `ToolRouter` 解析模型工具调用，并通过 `ToolRegistry` 分发。
- `CoreToolRuntime` 定义本地工具契约：spec、execution、hooks、telemetry、search metadata、argument diff consumers。
- `ToolCallRuntime` 调度工具调用，支持可并行工具、取消、abort responses，并对不安全工具串行执行。
- `spec_plan.rs` 从 core tools、MCP tools、dynamic tools、extension tools、deferred tools、hosted web/image tools、multi-agent tools 构建模型可见工具列表。
- shell execution 有 legacy 和 newer unified exec 两套 handler。
- `exec_command` 支持 process IDs、TTY、stdin continuation、yield time、output-token caps、remote environments、sandbox permissions、approval flow、apply-patch interception。
- `apply_patch.rs` 解析 freeform patch，发出 patch progress，计算写权限，并通过当前 environment filesystem 应用改动。
- `ExecutorFileSystem` 抽象 local/remote file operations。

Codex 暗示的最小 SWE Agent 工具集：

- Terminal command execution。
- Terminal output capture 与 truncation。
- Patch application。
- 通过 shell 和 environment filesystem abstraction 访问文件。
- 通过 `rg` 等 shell 工具搜索，加上 deferred tool discovery。
- Approval/permission flow。
- MCP tools/resources。

Codex 似乎并不主要依赖简单的模型可见 `read_file` 和 `write_file` 工具。它更依赖 shell、patch、MCP、environment filesystem abstractions。

## 高级能力

### 长期记忆

关键文件：

- `codex-rs/core/src/client.rs`
- `codex-rs/codex-api/src/endpoint/memories.rs`
- `codex-rs/core/src/stream_events_utils.rs`
- `codex-rs/memories/`

观察到的结构：

- `client.rs` 暴露 `summarize_memories`。
- API endpoint 调用 `/memories/trace_summarize`。
- stream handling 会检测 memory citations 并记录 usage。
- `codex-rs/memories/` crate 需要单独深读。

### Multi-Agent 工作流

关键文件：

- `codex-rs/core/src/agent/control.rs`
- `codex-rs/core/src/tools/handlers/multi_agents.rs`
- `codex-rs/core/src/tools/handlers/multi_agents_v2.rs`
- `codex-rs/core/src/thread_manager.rs`

观察到的结构：

- agent control 管理 spawn、send、wait、resume agents。
- multi-agent tools 把 subagent 操作暴露给 model/tool layer。
- `thread_manager.rs` 负责 thread creation、forking、resume、active thread registry。

### 后台任务

关键文件：

- `codex-rs/cloud-tasks/src/app.rs`
- `codex-rs/core/src/tasks/`

观察到的结构：

- cloud tasks 有独立 TUI/app，用于 task list、diff、apply flow、background enrichment。
- core tasks 包括 regular、compact、review、user shell command 等机制。

### Skills And Plugins

关键文件：

- `codex-rs/core/src/skills.rs`
- `codex-rs/core-skills/src/service.rs`
- `codex-rs/core/src/plugins/mod.rs`
- `codex-rs/core-plugins/src/manager.rs`

观察到的结构：

- skills 被加载并注入上下文。
- skill snapshots 按 cwd/config 缓存。
- plugins 可以贡献 skills、hooks、apps、MCP servers、marketplace metadata。

### Context Compression

关键文件：

- `codex-rs/core/src/compact.rs`
- `codex-rs/core/src/session/context_window.rs`
- `codex-rs/core/src/session/turn.rs`

观察到的结构：

- `compact.rs` 实现 manual 和 auto compaction。
- `context_window.rs` 计算 token status。
- `run_turn` 可以在 token limit 或 context-window request 需要时，在 turn 中途触发 compaction。

### Sandbox

关键文件：

- `codex-rs/core/src/sandboxing/mod.rs`
- `codex-rs/sandboxing/src/lib.rs`
- `codex-rs/sandboxing/src/manager.rs`
- `codex-rs/sandboxing/src/seatbelt.rs`
- `codex-rs/sandboxing/src/bwrap.rs`
- `codex-rs/sandboxing/src/landlock.rs`
- `codex-rs/sandboxing/src/windows.rs`

观察到的结构：

- core sandboxing 把 exec requests 适配成 sandbox execution。
- 平台实现覆盖 macOS Seatbelt、Linux bwrap/Landlock、Windows sandbox。

### MCP

关键文件：

- `codex-rs/core/src/mcp.rs`
- `codex-rs/core/src/session/mcp.rs`
- `codex-rs/core/src/tools/handlers/mcp.rs`

观察到的结构：

- MCP config 合并 user config、plugin registrations、app compatibility servers、extension overlays。
- runtime projection 决定某个 turn 可用哪些 MCP servers/tools。
- MCP tools 被适配成模型可见 tool specs 和 execution handlers。

### Terminal UI 与可观测性

关键文件：

- `codex-rs/tui/src/app.rs`
- `codex-rs/tui/src/chatwidget.rs`
- `codex-rs/otel/`

观察到的结构：

- TUI 消费 protocol events，并渲染 committed transcript cells 和 active streaming cells。
- App state 连接 session events、approvals、plugins、skills、settings、thread UI state。
- telemetry 和 OpenTelemetry crates 支撑生产级可观测性。

## 后续最值得精读的文件

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

## 缺口与不确定性

- `codex-rs/memories/` 下的 memory generation/consolidation 需要单独深读。
- sandbox 层只做了抽样，还没有逐个平台深读。
- multi-agent routing/control 已确认，但 agent graph persistence 还需要读 `codex-rs/agent-graph-store`。
- UI/event design 应该把 `codex-rs/app-server-protocol` 和 `codex-rs/tui/src/app/app_server_events.rs` 放在一起读。

