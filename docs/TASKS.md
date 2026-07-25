# Tasks

## Current Version: 02 — Task Decomposition

### Goal

Add session-scoped task scheduling so Coding Kid can decompose multi-step work,
track progress with a checklist, and continue from that list — without changing
the Version 01 loop shape.

### Included Scope

- A `todo` tool that replaces the full checklist on each call.
- Todo item fields: `content` and `status` (`pending` / `in_progress` /
  `completed`).
- Validation: non-empty list; valid statuses; at most one `in_progress`.
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

- Dataset: `SWE-bench/SWE-bench_Verified` (10 sampled instances under
  `evals/v02-baseline/verified_10_instances.json`).
- Version 01 official harness baseline: **5 / 10 resolved**.
- Compare Version 02 on the same instances, focusing on gains among the five
  Version 01 failures (empty patch / unresolved).

## Most Recently Completed Version

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

- Decide how to finish official V02 harness scoring (VPN once + keep images,
  cloud host, or behavioral-only for this iteration).
- Consider whether `todo` calls should be excluded from the 12-tool budget;
  V02 used todo on 10/10 but hit the budget on 10/10 and gold-file edits fell
  from 7/10 to 5/10 versus Version 01.

## Verification (in progress)

- `uv run --extra dev pytest -q`: 46 tests passed.
- `uv run --extra dev ruff check src tests`: passed.
- `uv run --extra dev ruff format --check src tests`: passed.
- Version 02 agent run on Verified × 10 completed: todo used on **10 / 10**.
- Behavioral comparison recorded in
  `evals/v02-baseline/VERIFIED_10_V02_SCORECARD.md`.
- Official Docker harness for V02 blocked by domestic mirror 404 / hung pulls
  of `swebench/sweb.eval.*` images.

## Current Constraints

- Stay inside Version 02 scope.
- Treat `versions/01-minimal-agent/` as a read-only historical checkpoint.
- Research only as needed to answer a concrete Version 02 question.
- Do not work on articles unless the user explicitly resumes article work.
- Follow `docs/VERSIONING.md` for routine commits and completed-version
  archives.
- Prefer domestic Docker registry mirrors for SWE-bench harness pulls; do not
  delete cached eval images after a successful pull when re-running harness.

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
