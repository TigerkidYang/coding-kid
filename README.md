# Coding Kid

Coding Kid is a small Python coding agent built for learning. The current
version shows the complete loop, a session todo checklist, and automatic
project-instruction loading:

```text
session context + project instructions + user input
  -> OpenRouter -> tool call -> local tool -> OpenRouter -> final answer
```

It runs as a plain terminal conversation and keeps history and todos only while
the process is running.

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

coding-kid       # latest completed core version (currently v3)
coding-kid v1    # minimal agent
coding-kid v2    # task decomposition
coding-kid v3    # context assembly
```

Numeric aliases such as `coding-kid 1` and `coding-kid 03` are also accepted.
To inspect the installed choices without starting a chat:

```powershell
coding-kid --list-versions
```

The command preserves the directory from which it was invoked. Version 03
therefore discovers that project's Git root and layered `AGENTS.md` files;
Versions 01 and 02 retain their original historical behavior.

During repository development, the module entry point accepts the same version
argument:

```powershell
uv run python -m coding_kid
uv run python -m coding_kid v1
```

Enter a coding task at the `You>` prompt. Enter `/exit` or `/quit` to stop.
Press `Ctrl+C` during an active task to interrupt it and return to the prompt.

Tool actions are printed before the final answer. Normal tool results stay in
the model context instead of filling the terminal; tool errors are still shown.
Tool action lines and tool results are bounded so one accidental command or
large file cannot flood the terminal or the next model request.

```text
You> Create hello.txt containing Hello
[tool] write: hello.txt
Coding Kid> Created hello.txt.
```

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

The tests use a fake provider for the complete agent loop, so they do not call
OpenRouter or spend API credits.

Every provider request uses the same session snapshot and cached project
instructions. These contextual messages are assembled only in the request copy;
they never enter or inflate the real conversation history. Todo changes and
recovery guidance are rendered again for each model/tool step.

If OpenRouter returns an empty response once, Coding Kid automatically asks the
model to continue. Repeated empty responses become a visible error instead of a
blank `Coding Kid>` answer. Failed and interrupted turns are removed from chat
history before the next prompt.

Each user turn executes at most 12 file/shell tool calls. Todo checklist updates
do not count toward that budget. Calls beyond the budget are skipped internally
and the model is instructed to answer from evidence already collected.
Repository-overview requests are guided toward selective inspection instead of
recursive trees, dependency scans, test runs, or Git archaeology.

Before returning a final answer, Coding Kid gives the model one chance to
reconcile any todo still marked `in_progress`. A second unreconciled final
answer becomes an explicit error rather than committing misleading progress.

## Current Limits

This teaching version intentionally has no TUI, persistent history, streaming,
automatic context compaction, token-window monitoring, long-term memory,
sandbox, approval flow, path restriction, or provider abstraction. It supports
only project `AGENTS.md` files: no global instructions, override files,
fallback names, includes, rules, skills, plugins, or MCP. Tools run with the
permissions of the current user. Use it only in a local test project you
control.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the module and data flow.

## Completed Versions

Independently runnable checkpoints are preserved under `versions/` and by
matching annotated tags. Version 01 is the minimal agent, Version 02 adds task
decomposition, and Version 03 adds context assembly. The installed launcher
bundles only their runtime source and shares one Python environment and one set
of third-party dependencies across all versions.
