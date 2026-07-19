# Coding Kid — Version 01: Minimal Agent

This directory is the independently runnable checkpoint for the first complete
version of Coding Kid. The matching annotated Git tag is
`version-01-minimal-agent`.

## Goal

Provide a small Python coding agent that accepts terminal input, sends the
conversation and tool definitions to GPT-5.6 Luna through OpenRouter, executes
local tools requested by the model, returns tool results to the model, and
prints a final answer.

## Included Scope

- A synchronous terminal conversation with process-local history.
- One OpenRouter provider using the OpenAI-compatible Responses API.
- Parsing for assistant text and multiple function calls.
- A sequential model/tool loop with empty-response recovery.
- Function-based `execute`, `read`, `write`, `search`, `patch`, and `delete`
  tools.
- Compact terminal tool activity with bounded model-visible tool results.
- Automated coverage for the provider, parser, tools, agent loop, CLI, and a
  complete multi-step file workflow.

This version intentionally excludes persistence, streaming, planning,
multi-agent workflows, sandboxing, approval flows, and additional providers.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- User environment variables `OPENROUTER_API_KEY` and `OPENROUTER_MODEL`

The verified model configuration at completion was:

```text
OPENROUTER_MODEL=openai/gpt-5.6-luna
```

Never store an API key inside this directory or commit it to Git.

## Setup and Run

Run these commands from this directory:

```powershell
uv sync --extra dev
uv run python -m coding_kid
```

Enter `/exit` or `/quit` to stop. Press `Ctrl+C` during an active task to return
to the prompt.

## Verify

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
uv run python -m compileall -q src
```

At completion, all 38 tests and all listed quality checks passed. Live GPT-5.6
Luna verification covered pure conversation, directory inspection, every file
tool, command execution, tool-error recovery, multiple actions in one turn,
multi-turn recall, and repeated non-empty final answers.

## Historical Status

This directory is a read-only teaching checkpoint. Current development remains
at the repository root and must not import from this archive.
