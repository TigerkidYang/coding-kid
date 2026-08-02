# Architecture

## Overview

The latest living core is Version 04. The launcher selects historical Versions
01–03 in isolated processes and runs Version 04 in process.

```text
launcher.py
  |-- v1/v2/v3 -> isolated bundled runtime process
  `-- v4/default -> cli.py -> context.py + context_manager.py
                                |              |
                                `----------> agent.py -> compaction.py
                                               |  |
                                               |  +-> parser.py
                                               +----> tools.py / provider.py
```

`cli.py` captures one immutable `SessionContext` and one mutable
`ContextManager` when a chat starts. `context.py` still owns stable context
assembly. `context_manager.py` owns the canonical transcript, bounded active
view, window budget, estimates, and compaction transitions.

## Version Launcher

`launcher.py` accepts `v1` through `v4` plus numeric aliases. No argument
selects `LATEST_VERSION`, currently `v4`. Invalid values fail before provider
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

Owns the outer conversation loop and creates one `SessionContext` and
`ContextManager` per terminal chat. It handles `/context`, `/compact`, tool and
context activity, and final answers. Failed or interrupted turns restore the
full managed conversation snapshot and todo state.

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

Owns the inner agent loop. It builds each request through the context manager,
performs proactive or reactive compaction when required, parses model output,
and executes tools sequentially. Empty-response recovery, the 64-call tool
budget, todo reconciliation, rollback behavior, and the 80-step loop bound
remain here.
Todo and recovery overlays are re-rendered for every provider request, so state
changes are visible immediately and no overlay is duplicated.

### `context_manager.py`

Owns the mutable Version 04 context lifecycle. `ConversationState` separates a
full process-local transcript from the active model view. Complete user and
model/tool segments provide safe retention boundaries. `ContextBudget` uses an
explicit window or one OpenRouter metadata lookup; provider input usage
calibrates a conservative request estimate. Missing metadata selects passive
mode rather than a guessed limit.

### `compaction.py`

Builds a structured handoff summary with no tools, retains the latest real user
request and recent complete model/tool segments, and atomically installs one
new active checkpoint. Summary errors leave state unchanged. An emergency
context-limit path can omit up to three oldest complete non-user segments from
the summary request without mutating the canonical transcript.

### `provider.py`

Sends one non-streaming OpenRouter request containing `instructions`, `input`,
tool definitions, and an optional output-token limit, then returns the raw
response. It also exposes narrow OpenRouter helpers for model context metadata,
input usage, and explicit context-window error classification.

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
4. The current bounded active conversation: one summary plus retained recent
   user and model/tool segments when compaction has occurred.
5. Current todo state and at most one recovery overlay.

Project context and overlays exist only in the provider request. They never
enter the mutable conversation list, so repeated model/tool steps do not grow
history with duplicate synthetic messages.

There is no persistent session, long-term memory, arbitrary project-file
injection, multi-tier trimming/collapse, or transcript storage.

## Tool Loop

1. The CLI appends a real user message.
2. The context manager estimates the next request and compacts first when the
   proactive threshold is reached.
3. The agent assembles a request copy from stable context, active history, and
   current dynamic overlays.
4. The provider returns assistant text and optional tool calls.
5. The agent executes requested tools and commits one complete model/tool
   segment to both transcript and active history.
6. Todo updates change the next request immediately.
7. The loop repeats until a valid final answer is returned or an existing
   recovery/limit rule ends the turn.
