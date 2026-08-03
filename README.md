# Coding Kid

Coding Kid is a small Python coding agent built for learning. The current
version shows the complete loop, a session todo checklist, automatic project
instructions, bounded conversation context, streamed model output, and a
full-screen terminal interface:

```text
session context + project instructions + user input
  -> OpenRouter stream -> typed events -> TUI
  -> tool call -> local tool -> OpenRouter stream -> final answer
```

Interactive terminals run a simplified Codex-style Textual interface. Piped or
redirected sessions fall back to the plain terminal conversation. Both keep
history and todos only while the process is running.

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

coding-kid       # latest living core version (currently v5)
coding-kid v1    # minimal agent
coding-kid v2    # task decomposition
coding-kid v3    # context assembly
coding-kid v4    # bounded context management
coding-kid v5    # streaming full-screen TUI
```

Numeric aliases such as `coding-kid 1` and `coding-kid 03` are also accepted.
To inspect the installed choices without starting a chat:

```powershell
coding-kid --list-versions
```

The command preserves the directory from which it was invoked. Versions 03–05
therefore discover that project's Git root and layered `AGENTS.md` files;
Versions 01 and 02 retain their original historical behavior. Version 05 is
the default while it is the living core version.

During repository development, the module entry point accepts the same version
argument:

```powershell
uv run python -m coding_kid
uv run python -m coding_kid v1
```

In the Version 05 TUI, enter a task in the bottom composer. `Enter` submits and
`Shift+Enter` inserts a newline. `Esc` or `Ctrl+C` requests interruption during
an active turn; `Ctrl+C` exits while idle. `/exit` and `/quit` also stop the
session. `/context` shows the current window status, and `/compact` creates a
manual context checkpoint.

The transcript streams assistant Markdown and records compact Codex-style
activity cells. Normal tool results stay in model context instead of filling
the interface; tool errors are shown. Tool action labels and model-visible
results remain bounded.

```text
› Create hello.txt containing Hello
• Edited hello.txt
• Created `hello.txt`.
```

## Streaming TUI

Version 05 keeps the Codex-inspired layout deliberately small: a session card,
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

This teaching version intentionally has no persistent history, long-term
memory, multi-tier compression, background tasks, multi-agent workflow,
sandbox, approval flow, path restriction, or provider abstraction. The TUI has
no queued input, attachments, mentions, reasoning display, mouse workflow,
themes, or trace files. It supports only project `AGENTS.md` files: no global
instructions, override files, fallback names, includes, rules, skills,
plugins, or MCP. Tools run with the permissions of the current user. Use it
only in a local test project you control.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the module and data flow.

## Teaching Versions

Completed checkpoints V1–V4 are preserved under `versions/` and by matching
annotated tags. The living Version 05 adds the Streaming TUI. The installed
launcher bundles V1–V4 runtime source and shares one Python environment and one
set of third-party dependencies across all versions.
