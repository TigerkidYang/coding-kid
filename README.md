# Coding Kid

Coding Kid is a small Python coding agent built for learning. The first version
shows the complete loop without hiding it behind a framework:

```text
user input -> OpenRouter -> tool call -> local tool -> OpenRouter -> final answer
```

It runs as a plain terminal conversation and keeps history only while the
process is running.

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

```powershell
uv sync --extra dev
```

## Run

```powershell
uv run python -m coding_kid
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

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

The tests use a fake provider for the complete agent loop, so they do not call
OpenRouter or spend API credits.

If OpenRouter returns an empty response once, Coding Kid automatically asks the
model to continue. Repeated empty responses become a visible error instead of a
blank `Coding Kid>` answer. Failed and interrupted turns are removed from chat
history before the next prompt.

Each user turn executes at most 12 tool calls. Calls beyond that budget are
skipped internally and the model is instructed to answer from evidence already
collected. Repository-overview requests are guided toward selective inspection
instead of recursive trees, dependency scans, test runs, or Git archaeology.

## First-Version Limits

This teaching version intentionally has no TUI, persistent history, streaming,
planning, sandbox, approval flow, path restriction, or provider abstraction.
Tools run with the permissions of the current user. Use it only in a local test
project you control.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the module and data flow.

## Completed Version

The independently runnable Version 01 checkpoint is preserved at
[`versions/01-minimal-agent/`](versions/01-minimal-agent/README.md) and by the
original annotated Git tag `version-01-minimal-agent`. The final verified
checkpoint is tagged `version-01-minimal-agent-fix2` without moving either
earlier tag.
