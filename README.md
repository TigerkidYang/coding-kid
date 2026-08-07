# Coding Kid

Coding Kid is a small Python coding agent built for learning. The current
version shows the complete loop, persistent project sessions, layered long-term
memory, pluggable Skills and MCP tools, continuous process-local terminal
sessions, worktree-isolated child Agents, bounded Web research, a controllable
turn loop, a session todo checklist, a permission-governed change workflow, a
fail-closed local sandbox, bounded conversation context, streamed model output,
and a full-screen terminal interface:

```text
session context + project instructions + Skill metadata + recalled memory
  + explicit Skill bodies + user input
  -> OpenRouter stream -> typed events -> TUI
  -> tool call -> built-in / execution session / Skill / MCP tool -> final answer
```

Interactive terminals run a simplified Codex-style Textual interface. Piped or
redirected sessions fall back to the plain terminal conversation. Version 06
stores independent project sessions and resumes their transcript, bounded
context, todos, and compaction state after a process restart.

At startup, Coding Kid finds the nearest Git root and loads each non-empty
`AGENTS.md` from that root down to the current directory. Deeper files appear
later, so they can refine the instructions inherited from their parents. The
loaded files are labeled with absolute source paths, share a 32 KiB content
budget, and remain fixed for that terminal chat. Restart Coding Kid to pick up
instruction changes.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop or another reachable Docker daemon for the default restricted
  Version 13 sandbox modes
- `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` environment variables
- Optional `BRAVE_SEARCH_API_KEY` for `web_search`; `web_fetch` needs no key

The API key must stay in the environment. Do not put it in this repository or
in a committed `.env` file. After setting a user-level environment variable on
Windows, open a new terminal so Python can inherit it.

`OPENROUTER_MODEL` must contain an OpenRouter model slug that supports tool
calling. Coding Kid uses the OpenAI Python SDK only as the small HTTP client for
OpenRouter's compatible API.

For an explicitly configured OpenAI-compatible Responses API, set
`CODING_KID_PROVIDER_BASE_URL`. Optional compatibility settings are
`CODING_KID_REASONING_EFFORT` and
`CODING_KID_DISABLE_MAX_OUTPUT_TOKENS=true`.
`CODING_KID_PROVIDER_TIMEOUT_SECONDS` overrides the default 120-second model
request timeout for slow high-effort endpoints. The existing key and model
variables remain unchanged so default OpenRouter behavior is backward
compatible.

## Version 16 Recoverable Autonomy

Version 16 keeps the explicit `execute + task` teaching architecture while
making recovery proportional to the environment. `required` preserves the
full fail-closed stage snapshot; `best-effort` can degrade to target-file
recovery and reports unknown shell/MCP effects honestly; `off` is available
only with unrestricted access. A provider-neutral `apply_patch` edits multiple
files atomically after complete validation, `diff` shares the same bounded
review evidence as `/changes`, and unfinished todos are visible resumable state
rather than a fatal completion gate.

## Version 15 Maintenance Release

Version 15 packages reliability fixes found through a complete Terminal-Bench
2.1 evaluation rather than introducing a new headline feature. It bounds broad
inspection in minimal containers, exposes only currently usable tools, supports
guarded checkpoints outside Git repositories, and improves slow
OpenAI-compatible Responses endpoints. The authorized k=1 run with
`gpt-5.6-luna` at max reasoning completed all 89 tasks and scored 50/89
(56.18%), with no exit-137 or final infrastructure failure. See
`docs/reports/terminal-bench-2.1-k1.md` for the exact protocol and limitations.

## Setup

For development inside this repository:

```powershell
uv sync --extra dev
```

To expose one `coding-kid` command that works from any project directory:

```powershell
uv tool install --force --editable C:\Users\littletiger\minicode
```

The editable installation follows later source changes without copying another
development checkout. `--force` refreshes the command entry point when Coding
Kid was installed previously.

## Run From Any Project

Change to the project Coding Kid should operate on, then select a completed
teaching version:

```powershell
cd D:\Projects\some-project

coding-kid       # latest living core version (currently v16; new session)
coding-kid v1    # minimal agent
coding-kid v2    # task decomposition
coding-kid v3    # context assembly
coding-kid v4    # bounded context management
coding-kid v5    # streaming full-screen TUI
coding-kid v6    # persistent sessions and long-term memory
coding-kid v7    # Skills, Plugins, and MCP tools
coding-kid v8    # process-local background shell tasks
coding-kid v9    # process-local multi-Agent workflows
coding-kid v10   # controllable turn runtime and active-turn steering
coding-kid v11   # fail-closed sandbox control
coding-kid v12   # permission-governed change workflow
coding-kid v13   # continuous interactive execution sessions
coding-kid v14   # isolated Agent collaboration and bounded Web research
coding-kid v15   # benchmark-driven reliability and portability hardening
coding-kid v16   # recoverable autonomy and atomic multi-file editing
```

Numeric aliases such as `coding-kid 1` and `coding-kid 03` are also accepted.
To inspect the installed choices without starting a chat:

```powershell
coding-kid --list-versions
```

The command preserves the directory from which it was invoked. Versions 03–16
therefore discover that project's Git root and layered `AGENTS.md` files;
Versions 01 and 02 retain their original historical behavior. Version 16 is
the default while it is the living core version.

During repository development, the module entry point accepts the same version
argument:

```powershell
uv run python -m coding_kid
uv run python -m coding_kid v1
```

Living Version 16 session selection is explicit:

```powershell
coding-kid --continue
coding-kid --resume 8f01c2ab
coding-kid --list-sessions
coding-kid --delete-session 8f01c2ab
```

The default creates a new session. IDs may be complete or unique prefixes.
Resume from the original directory with the original `OPENROUTER_MODEL`.
Deletion is soft: it hides the session but retains its JSONL evidence.

In the Version 16 TUI, enter a task in the bottom composer. `Enter` submits and
`Shift+Enter` inserts a newline. Submitting while work is active queues a steer
instruction FIFO and stops the current step before continuing with retained
completed evidence. Up to eight pending inputs are kept; a ninth remains in the
composer. `Esc` requests a hard interruption instead. `Ctrl+C` exits while
idle. `/context` shows the current window status, `/compact` creates a manual
context checkpoint, and `/session` or `/sessions` inspect persistence.
`/capabilities` reports loaded Skills and Plugins plus MCP server/tool status
without displaying environment values. `/permissions` distinguishes workflow,
approval, and sandbox state; `/mode`, `/changes`, and `/sandbox` inspect or
control their respective layers.

## Permission-Governed Change Workflow

Version 16 retains Version 12's permission workflow and defaults to
Implementation mode, Cautious approval, and the existing
`workspace-write` sandbox. These three settings are independent:

```powershell
coding-kid --mode plan --approval cautious
coding-kid --mode implementation --approval auto
coding-kid --mode review --approval full-access --sandbox read-only
```

Plan mode can inspect the project, ask up to three structured questions, and
submit a plan. Approval can enter Implementation with the current context or a
fresh model-visible context. Review receives the bounded stage summary and diff
but cannot modify the project or run arbitrary shell commands. Mode cannot
change during an active turn.

Cautious asks before writes, commands, deletion, background work, child Agents,
and external tools. Auto admits normal write/patch operations but still asks for
the other sensitive effects. Full Access removes ordinary prompts; it never
overrides workflow restrictions, protected metadata, or the sandbox. Prompts
support approve once, approve the same conservative action for this process,
deny with feedback, or abort. Grants and pending prompts do not survive restart.

Checkpoint policy is selected independently:

```powershell
coding-kid --checkpoint required
coding-kid --approval auto --checkpoint best-effort
coding-kid --approval full-access --sandbox danger-full-access --checkpoint off
```

`cautious` defaults to `required`; `auto` and `full-access` default to
`best-effort`. Required captures tracked and non-ignored untracked content and
fails closed if it cannot promise full rollback. Best effort uses the full
snapshot when practical, but non-Git or oversized projects protect only files
targeted by built-in edits. Shell, MCP, and unknown effects mark that coverage
partial; `/rollback --partial` is then required. Off stores no project bytes
and offers no application rollback. `/changes`, model `diff`, and Review mode
use one bounded evidence source.

For an already isolated disposable container or VM only, the explicit preset
below selects danger-full-access, full-access approval, and checkpoint off:

```powershell
coding-kid --dangerously-bypass-approvals-and-sandbox
```

It is intentionally unsafe on an ordinary host and prints a prominent warning.
Rollback always refuses while child/background work is active or when protected
files changed outside the last recorded Agent effect. Full and scoped rollback
restore the exact pre-stage dirty/untracked bytes, not Git HEAD.

## Sandbox Control

Version 16 retains Version 11's immutable startup policy. The default is a Docker-backed
workspace sandbox with network disabled:

```powershell
coding-kid                                      # workspace-write
coding-kid --sandbox read-only
coding-kid --sandbox workspace-write --sandbox-network
coding-kid --sandbox workspace-write --sandbox-image python:3.11-slim-bookworm
coding-kid --sandbox danger-full-access         # explicit host execution
```

Restricted startup fails if Docker is unavailable or the selected image has
not already been pulled; Coding Kid never retries the command on the host. Pull
the default image explicitly with `docker pull python:3.11-slim-bookworm`.
`workspace-write` mounts only the project into the command container and keeps
`.git` and `.coding-kid` read-only. `read-only` mounts the whole project
read-only. Built-in file tools apply the same project-root, link-resolution,
and metadata policy before touching the host filesystem.

Container commands receive a small fixed environment, bounded CPU, memory,
process count, and temporary storage. They do not inherit provider credentials,
mount the Docker socket, or receive network access unless
`--sandbox-network` is present. Root and child execution sessions inherit the
same policy. Restricted modes suppress MCP servers and
MCP tools because their local or remote effects cannot be enforced by this
Docker boundary; inert Skills and Plugin Skill metadata remain available.

`danger-full-access` retains the Version 10 host behavior and permissions. It
is intentionally explicit and is not a sandbox. The provider, session store,
and Skill loader remain trusted host-side control-plane services in every mode.

## Turn and Workflow Control

Version 10 makes continuation explicit and bounded: provider retries, output
limit recovery, empty-response recovery, todo reconciliation, step/tool/time
budgets, repeated-action stalls, steering, interruption, success, and failure
emit structured transitions. Completed tool rounds are retained across an
interrupted or failed turn; partial assistant streams are removed.

Consecutive built-in `read` and `search` calls may overlap in groups of four.
Their results still enter model history in requested order. Writes, patches,
deletes, terminal commands, task/Agent controls, Skills, MCP tools, and future
tools remain exclusive unless their registry metadata explicitly opts in.

## Multi-Agent Workflows

Version 16 retains Version 09's bounded child lifecycle and defaults writing
children to application-owned Git worktrees. `spawn_agent` selects `worktree`
or explicit `shared` isolation and may fork up to eight recent visible turns.
The `agent` tool lists, polls, waits, follows up, stops, reviews diffs,
reconciles conflicts, integrates changes, or explicitly discards a workspace.
Concurrent worktree children may edit the same path because neither sees
another child's unintegrated delta and the root remains unchanged.

A child receives its task prompt, project `AGENTS.md`, cwd-bound file and
terminal tools, Web research, Skills, MCP, and a private execution-session
manager. It does not receive long-term memory; an optional context fork excludes
tool calls, outputs, and hidden reasoning. Child processes and containers stop
when that run finishes, while a successful worktree and its manifest remain for
review.

Use `/agents` to inspect records and `/agent diff <id>`, `/agent integrate <id>`,
`/agent reconcile <id>`, `/agent discard <id> --confirm`, or `/agent stop <id>`
without a model call. Integration enters the normal stage checkpoint:
`/changes rollback` restores the root and makes the workspace reviewable again,
while `/changes accept` finalizes its cleanup. Interrupted application-owned
workspaces become orphaned evidence on restart instead of being deleted.

## Web Research

`web_search` queries Brave's fixed Search API and returns up to ten numbered
titles, snippets, and source URLs. Set `BRAVE_SEARCH_API_KEY` in the process
environment to enable it; the token is sent only in the provider header and is
never included in tool output. `web_fetch` needs no key and retrieves one public
text or HTML page with a 1 MB transfer limit, 30,000-character text limit, and
five-redirect limit.

Fetch accepts only HTTP(S) standard ports without embedded credentials. Every
DNS answer and redirect must remain globally routable, and connections are
pinned to a validated address. Local, private, reserved, mixed-address, binary,
compressed, and oversized responses fail closed. Page content is labeled
untrusted and carries its final URL for citation. In restricted sandboxes,
`--sandbox-network` is required; approval policy still governs both tools.

## Continuous Execution Sessions

Version 13 unifies short, yielded, background, and interactive commands. An
ordinary `execute` waits for `yield_time_ms` (10 seconds by default); if the
process is still alive, it returns a stable `task_<12 hex>` ID without rerunning
the command. `background=true` yields immediately. `interactive=true` allocates
a real Windows ConPTY or Unix PTY so a Python REPL, shell, or debugger can accept
later input and Ctrl+C.

`task` supports `list`, incremental `poll`, bounded `wait`, `write`,
`interrupt`, `stop`, and `check`. `check` runs a separate bounded command in the
same host environment or live Docker container; it is the evidence boundary for
service readiness. A running process is never automatically reported ready.
Plan and Review can only list/poll/wait. Cautious separately approves model
starts, writes, and checks; direct user commands are already explicit user
actions. Every operation remains inside the startup sandbox.

Use `/tasks`, `/task poll <id>`, `/task input <id> <text>`,
`/task interrupt <id>`, `/task check <id> <command>`, and `/task stop <id>` from
the CLI/TUI. At most eight sessions run and 32 records remain. Output preserves
a bounded head/tail and incremental recent window, with complete temporary log
files during the application lifetime. Shutdown removes logs and stops every
process tree/container. IDs and OS processes never survive restart; old IDs
return an explicit unknown/expired error. Completion updates UI state but does
not call the model automatically.

The transcript streams assistant Markdown and records compact Codex-style
activity cells. Normal tool results stay in model context instead of filling
the interface; tool errors are shown. Tool action labels and model-visible
results remain bounded.

```text
› Create hello.txt containing Hello
• Edited hello.txt
• Created `hello.txt`.
```

## Pluggable Capabilities

Version 07 separates capability packaging from execution:

- A Skill is a `SKILL.md` containing instructions. Coding Kid keeps only its
  name, description, and source in the prompt, then loads the complete body on
  `$skill-name`, `$plugin:skill-name`, or a model `skill(name)` call.
- MCP supplies structured external tools over stdio or Streamable HTTP. MCP
  tools enter the same per-session registry as built-in tools but do not use
  OpenAI strict schemas.
- A Plugin is an explicitly enabled local manifest that packages namespaced
  Skills and MCP server declarations. It adds no new execution protocol.

Standalone Skills live under `%CODING_KID_HOME%/skills/<name>/SKILL.md` or in
`.coding-kid/skills/<name>/SKILL.md` from the project root down to the current
directory. A minimal Skill is:

```markdown
---
description: Explain when and how this procedure should be used.
---

Complete instructions go here.
```

Executable capabilities are enabled only from
`%CODING_KID_HOME%/capabilities.json`; repository MCP configuration is never
started automatically. For example:

```json
{
  "plugins": [
    {"path": "C:/plugins/example", "enabled": true}
  ],
  "mcpServers": {
    "local": {
      "transport": "stdio",
      "command": "python",
      "args": ["server.py"],
      "env": {"TOKEN": "${DEMO_TOKEN}"},
      "required": false,
      "enabledTools": ["lookup"]
    }
  }
}
```

Environment substitution accepts only a complete `${ENV_NAME}` value. HTTP
headers sourced from the environment use `"envHeaders": {"Authorization":
"DEMO_AUTH_HEADER"}`. Configuration and connections are recaptured on every
process start or resume; credentials, connections, and MCP schemas are not
persisted. See
[`examples/plugins/readonly-inspector`](examples/plugins/readonly-inspector)
for a disabled-by-default Skill + MCP Plugin.

## Persistent Sessions

`CODING_KID_HOME` overrides the default `~/.coding-kid` storage directory.
Each project has append-only, hash-chained JSONL session logs plus a SQLite
index. A successful turn is flushed before the index advances. Startup can
rebuild missing or stale index entries, ignore a partial crash tail during
recovery, refuse a broken middle hash chain, and prevent concurrent writers.

Session logs preserve the provider-shaped transcript, active context,
compaction checkpoints, todos, and accounting state. Failed and interrupted
turns are audited but not replayed into model context. If a completed turn
cannot be saved, new turns are blocked until `/session save` succeeds.

Raw logs may contain prompts, tool results, code, or other sensitive material.
Protect the Coding Kid home directory and do not place credentials in prompts.
Obvious credential patterns are redacted before long-term-memory extraction,
but raw resumable logs remain lossless.

## Long-Term Memory

Version 06 separates exact history from selective memory:

```text
session JSONL -> per-session extraction -> consolidated typed memories
              -> bounded relevant recall for a later request
```

Automatic maintenance considers only closed or sufficiently idle, non-current
sessions; processes at most two per startup; and uses no tools. Invalid output
or provider failure leaves the prior memory set unchanged. Automatic extraction
creates only project memory. Cross-project user memory requires an explicit
`/remember --global ...` command.

Useful commands are:

```text
/memory
/memory search <query>
/memory sync
/remember <project fact or preference>
/remember --global <user preference>
/forget <memory-id>
```

`CODING_KID_MEMORY_MODE=auto|manual|off` controls maintenance and recall; the
default is `auto`. Automatic mode can make additional OpenRouter requests when
eligible prior sessions exist. `manual` keeps recall and explicit memory while
disabling automatic requests. `off` disables generation and recall.

Recall uses bounded lexical ranking rather than a vector database. At most five
memories enter only the current request and never become transcript or
compaction history. Memories are labeled as potentially stale; hidden citations
update usage metadata only when the model actually relies on them.

## Streaming TUI

Version 06 keeps the Codex-inspired layout deliberately small: a session card,
one scrolling transcript, an activity row, a multiline composer, and a footer
with model, cwd, and context remaining when known. It has no sidebar.

Provider text deltas update one active Markdown cell. The terminal provider
event still supplies one complete response before Coding Kid parses function
calls, records usage, or commits a model/tool round. Todo calls render an
`Updated Plan` snapshot with completed, active, and pending states. Reads and
searches appear as `Explored`; writes, patches, and deletes as `Edited`; shell
commands as `Ran`.

The agent runs in a worker thread while Textual owns terminal input and redraws.
Interruption is cooperative: an active provider stream closes immediately and
no later tool starts, while an already-running synchronous tool finishes before
the turn rolls back.

## Tools

- `execute`: run a short command or yield a stable execution-session ID. Set
  `background=true` for immediate yield, `interactive=true` for a real PTY, and
  `yield_time_ms` to bound only the initial wait. Turn interruption retains a
  root session instead of silently restarting it.
- `task`: list, incrementally poll, wait for, write to, Ctrl+C, health-check, or
  stop an execution session. Wait/check are bounded to 30 seconds. A check is
  explicit readiness evidence; liveness alone is not readiness.
- `read`: read a UTF-8 text file.
- `write`: create or completely overwrite a UTF-8 text file.
- `search`: search file names and text contents, returning at most 100 matches;
  generated directories and files larger than 1 MB are skipped.
- `patch`: replace one unique, exact text fragment in a file.
- `delete`: delete one file.
- `todo`: replace the full session task checklist. Use it for multi-step work.
  Statuses are `pending`, `in_progress`, and `completed`, with at most one item
  `in_progress`. A checklist has at most 20 items and each item has at most 200
  characters. Pass an empty list to clear it. New chats start empty, and a
  fully completed checklist is cleared after the final answer.
- `skill`: load one complete Skill body for the current turn. At most eight
  different Skills can load per turn; repeated calls do not reload the file.
- `mcp__<server>__<tool>` and
  `mcp__<plugin>__<server>__<tool>`: dynamically discovered MCP tools selected
  by configured filters, the 64-tool limit, and the context budget.

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

The tests use fake complete and streaming providers plus Textual's headless
driver, so they do not call OpenRouter or spend API credits.

Every provider request uses the same session snapshot and cached project
instructions. These contextual messages are assembled only in the request copy;
they never enter or inflate the real conversation history. Todo changes and
recovery guidance are rendered again for each model/tool step.

If the provider returns an empty response once, Coding Kid automatically asks
the model to continue. Repeated empty responses become a visible controlled
incomplete result instead of a blank answer or protocol crash. Failed and
interrupted turns retain complete model/tool evidence while removing incomplete
streaming projections before the next prompt.

Each user turn executes at most 64 built-in/MCP work calls. Todo checklist
updates and Skill loads do not count toward that budget. Calls beyond the
budget are skipped internally and the model is instructed to answer from
evidence already collected.
Repository-overview requests are guided toward selective inspection instead of
recursive trees, dependency scans, test runs, or Git archaeology.

Before returning a final answer, Coding Kid gives the model one soft chance to
reconcile any todo still marked `in_progress`. A second final answer is accepted
and the unfinished list remains visible and durable. Pending-only lists may end
immediately; completed lists are cleared automatically.

## Context Management

Version 04 keeps two in-memory views of the conversation. The canonical
transcript records what happened in the current process, while the bounded
active view is sent to the model. Stable runtime and project context, todos,
and recovery instructions remain canonical request layers and are regenerated
after compaction.

`CODING_KID_CONTEXT_WINDOW` may explicitly set the model window to an integer
of at least 16384 tokens. Without an override, Coding Kid looks up the selected
OpenRouter model once when the chat starts. If metadata is unavailable, chat
continues in passive mode: `/compact` and context-limit recovery remain
available, but proactive compaction is disabled.

Near the safe threshold, Coding Kid summarizes older history, preserves the
latest real user request and recent complete model/tool rounds, and continues
the same turn. A failed summary never replaces active context. Failed or
interrupted turns retain complete new protocol rounds and todo effects while
discarding incomplete streaming text and temporary failed-turn projections.

## Current Limits

This teaching version intentionally has no vector memory, remote memory sync,
encryption at rest, persistent or remote jobs, nested or remote Agents,
Agent worktrees, persistent/remote approval rules, marketplace, Plugin
downloader, OAuth, MCP Resources/Prompts, or provider abstraction. The TUI has
no queued attachments, mentions, reasoning display, mouse workflow, themes, or
trace files. It supports only project `AGENTS.md` files: no global instructions,
override files, fallback names, includes, or rules. It has no Hooks, Apps, or
LSP. Docker and the configured image remain trusted; this version does not
claim protection from a compromised daemon or kernel escape.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the module and data flow.

## Teaching Versions

Completed checkpoints V1–V15 are preserved under `versions/` and by matching
annotated tags. Version 13 remains the living default implementation. The
installed launcher bundles V1–V12 runtime source and shares one Python
environment and one set of third-party dependencies across all versions.
