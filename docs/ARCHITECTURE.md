# Architecture

## Overview

The latest core remains Version 03. An unnumbered launcher improvement adds a
version-selection boundary before the unchanged Version 03 agent runtime.

```text
launcher.py
  |-- v1/v2 -> isolated bundled runtime process
  `-- v3/default -> cli.py -> context.py -> agent.py -> provider.py
                                           |  |
                                           |  +-> parser.py
                                           +----> tools.py
```

`cli.py` captures one immutable `SessionContext` when a chat starts. `agent.py`
reuses that snapshot while it owns the model/tool loop. `context.py` discovers
project instructions and creates a fresh request copy for every model step.

## Version Launcher

`launcher.py` accepts `v1`, `v2`, or `v3` plus numeric aliases. No argument
selects `LATEST_VERSION`, currently `v3`. Invalid values fail before provider
initialization, and `--list-versions` reports the installed teaching runtimes.

The living package executes the latest runtime directly. Historical runtime
source lives under `coding_kid/_runtimes/vNN/coding_kid/`. The launcher starts
it in a child Python process with that fixed directory first on `PYTHONPATH`
and calls the snapshot's `cli.main()` directly. The child inherits cwd,
environment, standard input/output, and exit status. This preserves the
caller's arbitrary project directory while preventing the shared `coding_kid`
package name from resolving to a different teaching version.

Only Python runtime source is duplicated. All teaching versions share the same
installed interpreter and dependencies; archives, tests, evaluation data,
lockfiles, caches, and logs are not bundled in the wheel.

## Modules

### `launcher.py`

Owns teaching-version argument parsing and runtime isolation only. It does not
assemble prompts, initialize a provider, or alter agent behavior.

### `cli.py`

Owns the outer conversation loop and creates one `SessionContext` per terminal
chat. It appends user messages to in-memory history, shows tool activity, and
prints final answers. Failed or interrupted turns roll back messages and todo
state. A project-instruction read error stops initialization with the offending
path instead of starting a partial session.

### `context.py`

Owns context discovery, capture, and rendering.

- `SessionContext.capture(cwd)` resolves the absolute cwd, local ISO date,
  operating system, `cmd.exe` shell, configured model, nearest Git root, and
  project instructions.
- A `.git` directory or worktree file marks the nearest project root. Without a
  marker, only the current directory is considered.
- Non-empty `AGENTS.md` files are read from root to cwd with UTF-8 replacement
  decoding. Their contents share a 32 KiB root-first budget and carry absolute
  source labels and visible truncation markers.
- The captured value is frozen. File changes affect only a new chat.
- Request rendering combines the stable base/runtime instructions, cached
  project context, a request-only copy of conversation history, and current
  todo/recovery overlays.

### `agent.py`

Owns the inner agent loop. It asks `context.py` to assemble every request,
parses model output, executes tools sequentially, and commits conversation
history only after success. Empty-response recovery, the 12-call tool budget,
todo reconciliation, rollback behavior, and the 20-step loop bound remain here.
Todo and recovery overlays are re-rendered for every provider request, so state
changes are visible immediately and no overlay is duplicated.

### `provider.py`

Sends one non-streaming OpenRouter request containing `instructions`, `input`,
and tool definitions, then returns the raw response. It does not discover
files, assemble context, parse output, manage history, or abstract another
provider.

### `parser.py`

Extracts assistant text and function calls from one provider response.

### `tools.py`

Contains command, file, search, patch, delete, and todo functions plus their
schemas. Tool results are bounded before entering model context. The
process-local todo checklist is replace-based, bounded, and rolls back with a
failed turn.

## Request Assembly

Every provider request has this order:

1. Stable Coding Kid base instructions.
2. The immutable session environment snapshot.
3. Cached, source-labeled project instructions as a synthetic contextual user
   message.
4. A copy of real conversation and tool history.
5. Current todo state and at most one recovery overlay.

Project context and overlays exist only in the provider request. They never
enter the mutable conversation list, so repeated model/tool steps do not grow
history with duplicate synthetic messages.

There is no persistent session, automatic trimming, compaction, summarization,
token-window monitoring, arbitrary project-file injection, or long-term memory.

## Tool Loop

1. The CLI appends a real user message.
2. The agent assembles a request copy from session context, history, and current
   dynamic overlays.
3. The provider returns assistant text and optional tool calls.
4. The agent executes requested tools in order and appends matched results to
   real history.
5. Todo updates change the next request immediately.
6. The loop repeats until a valid final answer is returned or an existing
   recovery/limit rule ends the turn.
