# Coding Kid Version 05 — Streaming TUI

This teaching checkpoint adds a simplified Codex-style full-screen terminal
interface to Version 04's bounded, single-session context-management agent.

## Demonstrated Capability

- Streams visible assistant text into one live Markdown cell and consolidates
  the complete response once before parsing or tool execution.
- Shows user messages, assistant responses, tool activity, errors, and complete
  `Updated Plan` snapshots in a single scrollable transcript.
- Keeps Textual UI state separate from the canonical conversation, active
  context, and todo state owned by the agent.
- Displays real working, tool, compaction, and interruption status above a
  fixed composer.
- Supports `/context`, `/compact`, `/exit`, `/quit`, Esc interruption, and
  Ctrl+C interruption or exit.
- Rolls conversation, active context, and todo state back atomically after a
  failed or interrupted turn while retaining visible activity history.
- Falls back to the plain Version 04 chat when terminal input or output is not
  interactive.

The living repository passed all 140 deterministic tests, Ruff checks, wheel
inspection, and fresh-install V1–V5 launch checks. An explicitly authorized
live session also exercised the installed command in a real PTY against
OpenRouter, including multi-turn edits, todo updates, pytest, streamed Markdown,
manual context inspection and compaction, tool interruption, text-stream
interruption, rollback, recovery, and clean exit.

## Setup

Requirements:

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` for live use

```powershell
uv sync --extra dev
```

`CODING_KID_CONTEXT_WINDOW` may optionally set an explicit model context window
of at least 16384 tokens. Otherwise Coding Kid queries OpenRouter metadata once
and enters passive context mode if that lookup is unavailable.

## Run

Start Coding Kid inside the project directory it should work on:

```powershell
uv run coding-kid
```

Interactive terminals open the full-screen TUI. Enter submits, Shift+Enter adds
a line, and Esc interrupts the active turn. Use `/context` to inspect context
pressure, `/compact` for a manual checkpoint, and `/exit` or `/quit` to leave.

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

The archived tests cover streaming provider event shapes, typed turn events,
agent rollback, tool and todo visualization, Markdown consolidation, context
commands, compaction, interruption, plain fallback, and multiple terminal
sizes without making a live provider request.

## Intentional Limits

Version 05 has no persistent sessions, long-term memory, background tasks,
multi-agent work, MCP, skills, plugins, permissions, sandboxing, input queue,
attachments, shell mode, mouse interaction, Web UI, or streamed reasoning and
tool arguments. A synchronous tool already in progress is allowed to reach its
boundary after interruption is requested.

The cross-version launcher remains an unnumbered root-project facility. This
archive starts Version 05 directly and does not recursively carry the V1–V4
bundled runtimes.

## Git Checkpoint

Matching annotated tag: `version-05-streaming-tui`.
