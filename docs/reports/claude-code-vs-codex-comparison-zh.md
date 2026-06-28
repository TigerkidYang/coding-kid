# Claude Code 源码归档 vs OpenAI Codex

日期：2026-06-29

来源：

- Claude Code source archive：`research/repos/claude-code`
- OpenAI Codex：`research/repos/codex`

## 高层对比

Claude Code 和 Codex 都很有价值，但它们在这个项目里应该承担不同角色。

Claude Code 更适合研究产品机制和功能广度。它的源码归档暴露了很多具体的 TypeScript/TSX 模块，覆盖 tools、memory、subagents、background tasks、skills/plugins、MCP、compaction、sandboxing、Ink terminal UI。但这份归档不能直接构建。

Codex 更适合研究工程架构。它的官方仓库有一个很大的 Rust workspace，清楚拆出了 core session logic、tool runtime、sandboxing、TUI、plugins、skills、MCP、thread management、protocol events。它是更强的生产结构参考。

## Core Loop

Claude Code：

- 主 loop 在 `src/query.ts`。
- 高层 orchestration 在 `src/QueryEngine.ts`。
- 形状：engine 提交 message -> 组装 context -> 流式模型输出 -> 识别 tool calls -> 执行工具 -> 追加结果 -> 继续。
- loop 是 async generator，并且整合 compaction、fallback、stop hooks、aborts、token budgets、tool-result budgets。

Codex：

- 主 loop 在 `codex-rs/core/src/session/turn.rs`。
- session handling 在 `codex-rs/core/src/session/session.rs` 和 `handlers.rs`。
- 形状：thread/session/turn -> build prompt -> stream Responses API events -> parse output items -> execute tools -> append outputs -> continue。
- 它在 thread、session、turn、input queue、model client、UI protocol events 之间有更强的边界。

项目启发：

Python MVP 可以借鉴 Claude Code 的紧凑 async-loop 形状。长期架构则应该借鉴 Codex 的 thread/session/turn/event 边界。

## Tool Calling

Claude Code：

- 中央抽象：`src/Tool.ts`。
- registry：`src/tools.ts`。
- execution：`src/services/tools/toolExecution.ts`。
- orchestration：`src/services/tools/toolOrchestration.ts`。
- streaming execution：`src/services/tools/StreamingToolExecutor.ts`。
- 有显式的模型可见文件工具：Read、Edit、Write、Glob、Grep。

Codex：

- router：`codex-rs/core/src/tools/router.rs`。
- registry：`codex-rs/core/src/tools/registry.rs`。
- parallel runtime：`codex-rs/core/src/tools/parallel.rs`。
- tool plan/spec builder：`codex-rs/core/src/tools/spec_plan.rs`。
- terminal execution：`unified_exec/exec_command.rs`。
- patch editing：`apply_patch.rs`。
- file system abstraction：`codex-rs/file-system/src/lib.rs`。

项目启发：

Python MVP 阶段，Claude Code 的显式 `Tool` 抽象和文件工具更容易模仿。成熟版本可以学习 Codex 的 registry/router/runtime 拆分。

## Terminal 与文件操作

Claude Code：

- `BashTool` 很产品化：command semantics、sandbox decisions、backgrounding、大输出持久化、image output、stdout/stderr handling、progress UI。
- 文件工具要求 prior read，并防止 stale writes。
- Grep/Glob 是一等工具。

Codex：

- terminal execution 和 approvals、sandbox permissions、remote environments、TTY/stdin continuation、process IDs、output token caps 集成。
- 文件编辑主要是 patch-oriented。
- 文件访问通过 local/remote environment file systems 抽象。

项目启发：

先从 Claude Code 的 Bash/Read/Edit/Write/Grep/Glob 模型可见工具集开始。后面再借鉴 Codex 的 patch-first editing 和 environment filesystem abstractions。

## 长期记忆

Claude Code：

- 文件记忆路径很清楚：`src/memdir/memdir.ts`、`src/context.ts`、`src/services/autoDream/autoDream.ts`。
- `autoDream` 特别值得研究：它会在时间/session gate 之后做后台 consolidation。

Codex：

- 记忆系统存在，但需要更深读。
- 已确认的点包括 `summarize_memories`、`/memories/trace_summarize`、memory citations、`codex-rs/memories/`。

项目启发：

长期记忆先看 Claude Code 更合适。它的文件记忆和自动 consolidation 很贴合我们当前 AGENTS/docs 的项目记忆策略。

## Multi-Agent 与后台工作

Claude Code：

- `AgentTool` 启动 sync/async agents、fork subagents、remote agents、worktree-isolated agents。
- 后台 shell 和 agent tasks 都有明确 task objects。

Codex：

- multi-agent control 和 thread management、tool handlers 绑定更紧。
- `thread_manager.rs` 和 `agent/control.rs` 是重要架构参考。
- cloud tasks 展示了后台任务的独立产品界面。

项目启发：

Claude Code 更适合研究 subagent 作为用户可见工具时的体验。Codex 更适合研究持久 thread/task 架构。

## Skills、Plugins 与 MCP

Claude Code：

- Skills 从 `SKILL.md` frontmatter 加载，可包含 path triggers、allowed tools、hooks、shell blocks、arguments。
- Plugins 可以增加 commands、agents、hooks、marketplace/session behavior。
- MCP config 合并 global/project/managed/plugin sources，并把 MCP tools 包装进同一套 `Tool` 抽象。

Codex：

- Skills 和 plugins 被拆到专门 crate/service。
- Plugins 可以贡献 skills、hooks、apps、MCP servers、marketplace metadata。
- MCP 通过 config/session/tool-handler layers 投射到 turns。

项目启发：

Python 早期可以先用 Claude Code 更简单的 skill/plugin loading model。后期 Codex 的 crate/service 分层能指导我们避免 plugin system 污染 core loop。

## Context Compression

Claude Code：

- 多种 compaction strategy 直接接在 `query.ts` 中：snip、microcompact、context collapse、autocompact、recovery。

Codex：

- `compact.rs` 和 `context_window.rs` 提供了更干净的架构面。
- `run_turn` 在 token limit 或 context-window request 需要时触发 compaction。

项目启发：

Claude Code 适合看真实产品里到底有哪些压缩场景。Codex 更适合学习干净边界怎么设计。

## Sandbox

Claude Code：

- sandbox decision 靠近 Bash execution，把 settings/permissions 转成 runtime config。

Codex：

- sandbox 是一等跨平台子系统，有 macOS、Linux、Windows 实现。

项目启发：

MVP 阶段先实现简单 permission 和 workspace-boundary checks。成熟版本再参考 Codex 的 sandbox 架构。

## Terminal UI 与可观测性

Claude Code：

- Ink/React terminal UI。
- `ContextVisualization.tsx` 对“给用户展示 context、memory、MCP tools、skills、agents、collapse state”很有参考价值。
- 源码归档里有 tracing/profiling utilities。

Codex：

- Rust TUI，基于 protocol events 驱动渲染。
- `chatwidget.rs` 消费 session events，渲染 committed/active cells。
- 集成 OpenTelemetry。

项目启发：

Claude Code 更适合研究用户可见 terminal affordances。Codex 更适合研究 event-driven UI architecture。

## 推荐阅读顺序

1. Claude Code `src/query.ts` 和 Codex `codex-rs/core/src/session/turn.rs` 对照读。
2. Claude Code `Tool.ts`/`toolExecution.ts` 和 Codex `tools/registry.rs`/`tools/router.rs` 对照读。
3. Claude Code `BashTool` 和 Codex `unified_exec/exec_command.rs` 对照读。
4. Claude Code file tools 和 Codex `apply_patch.rs` 对照读。
5. Claude Code `autoDream` 和 Codex `memories/` 对照读。
6. Claude Code `AgentTool` 和 Codex `agent/control.rs`、`thread_manager.rs` 对照读。
7. Claude Code `ContextVisualization.tsx` 和 Codex `tui/src/chatwidget.rs` 对照读。

## 对我们 Python Agent 的设计建议

MVP：

- 使用受 Claude Code 启发的简单 async loop。
- 实现显式工具：Bash、Read、Write、Edit、Glob、Grep、Todo。
- 用仓库文件做 durable memory。
- 权限保持简单，但要用户可见。
- 在引入服务化之前，先把所有状态存在普通对象/文件里。

下一阶段：

- 引入类似 Codex 的边界：Thread、Session、Turn、ToolRegistry、ToolRuntime、EventBus。
- 加入 patch-first editing。
- 加入 context-window accounting 和 compaction。
- 加入 background tasks 和 subagents。

成熟阶段：

- 加入 sandbox profiles。
- 加入 plugin/skill/MCP registration。
- 加入 event-driven terminal UI。
- 加入 observability 和 trace logs。
- 加入类似 Claude Code `autoDream` 的 memory consolidation，但要结合我们自己的 repository documentation strategy。

