# Coding Kid

Coding Kid is a small Python coding agent built for learning. The current
version shows the complete loop, persistent project sessions, layered
long-term memory, a session todo checklist, bounded conversation context,
streamed model output, and a full-screen terminal interface:

```text
session context + project instructions + recalled memory + user input
  -> OpenRouter stream -> typed events -> TUI
  -> tool call -> local tool -> OpenRouter stream -> final answer
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
- `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` environment variables

The API key must stay in the environment. Do not put it in this repository or
in a committed `.env` file. After setting a user-level environment variable on
Windows, open a new terminal so Python can inherit it.

`OPENROUTER_MODEL` must contain an OpenRouter model slug that supports tool
calling. Coding Kid uses the OpenAI Python SDK only as the small HTTP client for
OpenRouter's compatible API.

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

coding-kid       # latest living core version (currently v6; new session)
coding-kid v1    # minimal agent
coding-kid v2    # task decomposition
coding-kid v3    # context assembly
coding-kid v4    # bounded context management
coding-kid v5    # streaming full-screen TUI
coding-kid v6    # persistent sessions and long-term memory
```

Numeric aliases such as `coding-kid 1` and `coding-kid 03` are also accepted.
To inspect the installed choices without starting a chat:

```powershell
coding-kid --list-versions
```

The command preserves the directory from which it was invoked. Versions 03–06
therefore discover that project's Git root and layered `AGENTS.md` files;
Versions 01 and 02 retain their original historical behavior. Version 06 is
the default while it is the living core version.

During repository development, the module entry point accepts the same version
argument:

```powershell
uv run python -m coding_kid
uv run python -m coding_kid v1
```

Version 06 session selection is explicit:

```powershell
coding-kid --continue
coding-kid --resume 8f01c2ab
coding-kid --list-sessions
coding-kid --delete-session 8f01c2ab
```

The default creates a new session. IDs may be complete or unique prefixes.
Resume from the original directory with the original `OPENROUTER_MODEL`.
Deletion is soft: it hides the session but retains its JSONL evidence.

In the Version 06 TUI, enter a task in the bottom composer. `Enter` submits and
`Shift+Enter` inserts a newline. `Esc` or `Ctrl+C` requests interruption during
an active turn; `Ctrl+C` exits while idle. `/exit` and `/quit` also stop the
session. `/context` shows the current window status, `/compact` creates a
manual context checkpoint, and `/session` or `/sessions` inspect persistence.

The transcript streams assistant Markdown and records compact Codex-style
activity cells. Normal tool results stay in model context instead of filling
the interface; tool errors are shown. Tool action labels and model-visible
results remain bounded.

```text
› Create hello.txt containing Hello
• Edited hello.txt
• Created `hello.txt`.
```

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

- `execute`: run one foreground Windows `cmd.exe` command with a 2-minute
  timeout.
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

If OpenRouter returns an empty response once, Coding Kid automatically asks the
model to continue. Repeated empty responses become a visible error instead of a
blank `Coding Kid>` answer. Failed and interrupted turns are removed from chat
history before the next prompt.

Each user turn executes at most 64 file/shell tool calls. Todo checklist updates
do not count toward that budget. Calls beyond the budget are skipped internally
and the model is instructed to answer from evidence already collected.
Repository-overview requests are guided toward selective inspection instead of
recursive trees, dependency scans, test runs, or Git archaeology.

Before returning a final answer, Coding Kid gives the model one chance to
reconcile any todo still marked `in_progress`. A second unreconciled final
answer becomes an explicit error rather than committing misleading progress.

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
interrupted turns restore conversation and todo state to the start of the turn.

## Current Limits

This teaching version intentionally has no vector memory, remote memory sync,
encryption at rest, generic background-task framework, multi-agent workflow,
sandbox, approval flow, path restriction, or provider abstraction. The TUI has
no queued input, attachments, mentions, reasoning display, mouse workflow,
themes, or trace files. It supports only project `AGENTS.md` files: no global
instructions, override files, fallback names, includes, rules, skills,
plugins, or MCP. Tools run with the permissions of the current user. Use it
only in a local test project you control.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the module and data flow.

## Teaching Versions

Completed checkpoints V1–V6 are preserved under `versions/` and by matching
annotated tags. The living Version 06 adds persistent sessions and long-term
memory. The installed launcher bundles V1–V5 runtime source and shares one
Python environment and one set of third-party dependencies across all versions.
