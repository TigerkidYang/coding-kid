# Coding Kid Version 04 — Context Management

This teaching checkpoint evolves Version 03's bounded context assembly into
bounded, single-session context management.

## Demonstrated Capability

- Keeps a complete in-memory canonical transcript and a separate bounded view
  for model requests.
- Represents real user messages and complete model/tool rounds as protocol-safe
  retention units.
- Uses an explicit context window or OpenRouter model metadata, conservative
  preflight estimates, and provider input usage calibration.
- Compacts proactively near the safe threshold, manually through `/compact`,
  or once after an explicit context-window error.
- Produces an authoritative structured handoff, preserves the latest user
  request and budgeted recent rounds, and avoids repeating completed tool work.
- Keeps project instructions, todos, and recovery overlays canonical so they
  are regenerated after compaction.
- Replaces active context atomically and restores conversation plus todo state
  after failed or interrupted turns.
- Exposes window and compaction state through `/context`.

The deterministic suite passed at 115/115 in the living repository; this
self-contained core archive excludes the separate cross-version launcher tests.
A paired live slice on `openai/gpt-5.6-luna` passed Version 04 process and
outcome at 3/3, including two consecutive compactions. The corrected real CLI
smoke compacted once, reused summarized evidence, wrote and verified the exact
requested result, and finished using 6 model requests.

## Setup

Requirements:

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` for live use

```powershell
uv sync --extra dev
```

`CODING_KID_CONTEXT_WINDOW` may optionally set the model context window to an
integer of at least 16384 tokens. Otherwise Version 04 looks up the selected
OpenRouter model once at chat startup and falls back to passive mode if metadata
is unavailable.

## Run

Start Coding Kid inside the project directory it should work on:

```powershell
uv run python -m coding_kid
```

Use `/context` to inspect context pressure and `/compact` to request a manual
checkpoint. Use `/exit` or `/quit` to leave the chat.

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

The archived tests cover accounting, retention boundaries, proactive/manual/
reactive compaction, summary validation, emergency reduction, repeated
compaction, provider usage calibration, passive mode, rollback, CLI commands,
and all inherited agent/tool behavior without a live API call.

## Intentional Limits

Version 04 has no persistent or cross-session history, long-term memory,
retrieval, multi-agent context, background compaction, multiple compression
tiers, user-defined summary prompt, separate summary model, TUI, sandbox,
approval flow, MCP, skills, plugins, or provider abstraction.

The cross-version launcher remains an unnumbered root-project facility. This
archive starts Version 04 directly and therefore does not recursively carry
the V1–V3 bundled runtimes.

## Git Checkpoint

Matching annotated tag: `version-04-context-management`.
