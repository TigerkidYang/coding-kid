# Tasks

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

- Wait for the user to define the next version's goal, included scope, excluded
  scope, and completion criteria.

## Verification

- `uv run --extra dev pytest -q`: 42 tests passed.
- `uv run --extra dev ruff check src tests`: passed.
- `uv run --extra dev ruff format --check src tests`: passed.
- `uv run python -m compileall -q src`: passed.
- Both `uv run python -m coding_kid` and `uv run coding-kid` started and exited
  normally in terminal smoke tests.
- A real OpenRouter request returned the expected text response.
- A real OpenRouter model/tool/model loop called the `read` tool and returned a
  final answer.
- A live terminal read showed the compact tool action without printing the raw
  file contents.
- A live request to list the repository root used the Windows `dir` command,
  completed the model/tool/model loop, and returned a concise final answer.
- Empty searches are rejected, search results stop after 100 matches, and
  interrupting an active task returns to the prompt without a traceback.
- Empty final responses, partial-history rollback, bounded tool output, search
  pruning, provider timeouts, and compact terminal rendering have regression
  coverage.
- Foreground commands have a fixed two-minute execution timeout, with regression
  coverage for the configured value and timeout error path.
- An eight-turn live GPT-5.6 Luna matrix passed pure chat, directory listing,
  write/read, patch/read, search, missing-file recovery, delete verification,
  and multi-turn recall with nine tool calls.
- One live Luna request completed `write -> patch -> read -> delete -> execute`
  in a single user turn and returned a non-empty final answer.
- Five independent live Luna directory-listing runs completed with non-empty
  answers; all five used the expected model/tool/model sequence.
- The original Chinese directory-listing prompt passed through the real CLI and
  returned its final answer without requiring a second user prompt.
- A live identity check returned `openai/gpt-5.6-luna` instead of inventing a
  different model name.
- Three strict live runs of `理解一下这个仓库` completed in 25.2–31.5 seconds
  with 9–12 executed tools, no unknown tools, empty parameters, recursive tree,
  tests, Git inspection, tool errors, or blank final answers.
- The same repository-understanding request passed through the real CLI with a
  direct evidence-based final answer. Tool-budget recovery was exercised in
  both automated and live tests.

## Current Constraints

- Do not define later versions.
- Do not begin implementation until the user defines the next version.
- Treat `versions/01-minimal-agent/` as a read-only historical checkpoint.
- Research only as needed to answer a concrete question.
- Do not work on articles unless the user explicitly resumes article work.
- Follow `docs/VERSIONING.md` for routine commits and completed-version
  archives.

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
