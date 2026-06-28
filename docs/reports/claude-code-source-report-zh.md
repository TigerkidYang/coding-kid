# Claude Code 源码归档研究报告

日期：2026-06-29

本地源码：`research/repos/claude-code`

## 总体判断

这份归档看起来是连贯的，而且很适合做技术研究，但它不是一个可以直接构建运行的项目。它在 `src/` 下有一棵很大的 TypeScript/TSX 源码树，能看到 query 编排、工具系统、MCP、记忆、子代理、后台任务、沙箱、terminal UI 等子系统。

根目录缺少 `package.json` 和 `tsconfig.json`，所以应该把它当成“恢复出来的源码归档”来阅读，而不是当成可依赖的上游工程。

## 核心 Agent Loop

关键文件：

- `src/query.ts`
- `src/QueryEngine.ts`
- `src/services/api/claude.ts`
- `src/utils/messages.ts`
- `src/utils/queryContext.ts`
- `src/constants/prompts.ts`
- `src/context.ts`

观察到的结构：

- `query()` 把主要工作交给 `queryLoop()`，这是核心 async generator loop。
- loop 会流式接收模型输出，识别 `tool_use` block，执行工具，追加 tool result，然后继续循环直到结束条件出现。
- loop 还处理 fallback model retry、abort、最大轮数、token budget、tool-result budget、上下文压缩、stop hooks。
- `QueryEngine.ts` 在底层 loop 外面包了一层会话状态：可变 messages、已读文件 cache、permission denials、usage、transcript 持久化、系统 prompt 组装、skills/plugins 加载、SDK message 标准化。
- prompt 组装会合并默认系统 prompt、工具相关 prompt 段落、git status、日期、类似 CLAUDE.md 的上下文、MCP instructions、output styles、自定义追加 prompt。

核心形状：

`Engine.submitMessage()` -> 处理用户输入和上下文 -> `query()` loop -> 流式模型输出 -> 识别工具调用 -> 执行工具 -> 追加工具结果 -> 继续。

## Tool Calling

关键文件：

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

观察到的结构：

- `Tool.ts` 定义中央工具抽象：name、input schema、call、prompt、权限检查、输入校验、是否只读、并发安全性、结果大小、MCP 标记、UI render hooks。
- `tools.ts` 组装内置工具池。
- `toolExecution.ts` 分发单个工具调用：schema 校验、pre-tool hooks、权限解析、工具执行、进度、错误转 tool-result message。
- `toolOrchestration.ts` 批量处理工具调用：安全/只读工具并行执行，不安全工具串行执行。
- `StreamingToolExecutor.ts` 可以在 tool-use block 还在流式生成时就启动工具，并按顺序缓存结果。
- `BashTool` 支持 timeout、流式进度、后台执行、大输出持久化、沙箱包装、CWD 恢复、图片输出、命令语义分析、stdout/stderr 处理。
- 文件 edit/write 工具要求先读过文件，并且当文件发生变化时会拒绝 stale write。

这份归档暗示的最小 SWE Agent 工具集：

- Bash / terminal 执行。
- 文件读取。
- 文件编辑。
- 文件写入。
- Glob。
- Grep。
- Todo 或 planning tool。
- 任务输出 / 后台任务读取。

## 高级能力

### 长期记忆

关键文件：

- `src/memdir/memdir.ts`
- `src/context.ts`
- `src/services/autoDream/autoDream.ts`

观察到的结构：

- 文件记忆使用类似 `MEMORY.md` 的 prompt 机制。
- `context.ts` 把类似 CLAUDE.md 的文件加载进用户上下文。
- `autoDream.ts` 在时间/session gate 之后，以 forked agent 的方式运行后台记忆 consolidation。

### Multi-Agent 工作流

关键文件：

- `src/tools/AgentTool/AgentTool.tsx`
- `src/tools/AgentTool/runAgent.ts`
- `src/tools/AgentTool/forkSubagent.ts`

观察到的结构：

- `AgentTool` 可以启动同步/异步 agent、teammates、remote agents、worktree-isolated agents、fork subagents。
- `runAgent.ts` 构造子代理上下文、工具池、权限、transcripts、MCP、hooks，然后调用 `query()`。
- forked worker 可以继承父上下文/系统 prompt，这对 prompt cache 共享可能有用。

### 后台任务

关键文件：

- `src/tasks/LocalShellTask/LocalShellTask.tsx`
- `src/tasks/LocalAgentTask/LocalAgentTask.tsx`
- `src/tasks/RemoteAgentTask/RemoteAgentTask.tsx`
- `src/tools/TaskOutputTool/TaskOutputTool.tsx`

观察到的结构：

- shell task 和 agent task 都有明确的 lifecycle object。
- 后台命令可以发出 task notification，并把输出写入文件。
- `TaskOutputTool` 可以轮询任务状态，不过较新的流程可能更偏向直接读取输出文件。

### Skills And Plugins

关键文件：

- `src/skills/loadSkillsDir.ts`
- `src/tools/SkillTool/SkillTool.tsx`
- `src/utils/plugins/pluginLoader.ts`

观察到的结构：

- Skill 从 `SKILL.md` frontmatter 加载，支持 path triggers、allowed tools、hooks、shell blocks、arguments。
- Plugin 可以提供 commands、agents、hooks，以及 marketplace/session cached behavior。

### Context Compression

关键文件：

- `src/services/compact/autoCompact.ts`
- `src/services/compact/compact.ts`
- `src/services/compact/microCompact.ts`
- `src/services/compact/sessionMemoryCompact.ts`
- `src/query.ts`

观察到的结构：

- query loop 把 snip、microcompact、context collapse、autocompact、reactive recovery 都接进执行流程。
- `autoCompact.ts` 判断何时 compact，并选择具体压缩路径。

### Sandbox

关键文件：

- `src/utils/sandbox/sandbox-adapter.ts`
- `src/tools/BashTool/shouldUseSandbox.ts`

观察到的结构：

- sandbox config 从 settings/permissions 推导出来。
- 覆盖 filesystem allow/deny、network domains、危险 settings 路径、git worktree 处理、依赖检查。

### MCP

关键文件：

- `src/services/mcp/config.ts`
- `src/services/mcp/client.ts`
- `src/tools/MCPTool/MCPTool.ts`

观察到的结构：

- MCP config 合并 global、project、managed、plugin server configs。
- client 支持 stdio、SSE、HTTP、WebSocket、SDK transports。
- MCP tools 被包装进同一套 `Tool` 抽象。

### Terminal UI 与可观测性

关键文件：

- `src/components/App.tsx`
- `src/screens/REPL.tsx`
- `src/components/ContextVisualization.tsx`
- `src/utils/telemetry/sessionTracing.ts`
- `src/utils/telemetry/perfettoTracing.ts`
- `src/utils/queryProfiler.ts`
- `src/utils/headlessProfiler.ts`

观察到的结构：

- UI 是 Ink/React terminal app。
- `ContextVisualization.tsx` 会展示 token/context 使用、memory files、MCP tools、skills、agents、collapse state。
- 有 session 和 query 执行相关的 tracing/profiling hooks。

## 后续最值得精读的文件

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

## 缺口与不确定性

- 因为根目录缺少构建元数据，这份归档不能直接编译。
- 很多模块由 feature gate 控制，所以真实发布版本里哪些路径启用还不清楚。
- 一些 TSX 文件看起来像被转换过，或者带有编译器输出痕迹。
- MCP、plugins、sandbox runtime、telemetry、model API 行为依赖归档中没有包含的外部包/服务。
- compaction 内部、MCP tool wrapping、权限解析、hook 执行、Ink rendering pipeline 还需要继续深读。

