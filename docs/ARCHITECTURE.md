# Architecture

## Overview

Version 02 keeps the synchronous terminal coding agent from Version 01 and adds
session-scoped task decomposition through a `todo` tool.

```text
cli.py
  -> agent.py
       -> provider.py
       -> parser.py
       -> tools.py  (file/shell tools + todo checklist state)
```

## Modules

### `cli.py`

Owns the outer conversation loop. It reads terminal input, appends user
messages to one in-memory list, shows tool activity, and prints the final model
answer. Failed or interrupted turns are rolled back before accepting the next
prompt, and blank answers are never printed as successful responses.

### `agent.py`

Owns the inner agent loop. It sends the current context to the provider, keeps
the raw model output in history, executes requested tools sequentially, appends
their results, and repeats until the model returns no more tool calls. Changes
to conversation history are committed only after a successful final answer. A
single empty model response is retried; a repeated empty response becomes an
explicit error. The retry receives a direct recovery instruction rather than
the unchanged prompt. A turn executes at most 12 tools; later requested calls
receive matched skipped outputs and the model is instructed to answer from the
evidence already available.

### `provider.py`

Makes one non-streaming OpenRouter request through its OpenAI-compatible API and
returns the raw response. It does not parse output, manage history, execute
tools, or abstract a second API provider. Requests use a 120-second timeout and
the client's two automatic retries.

### `parser.py`

Extracts assistant text and function calls from one provider response. A parsed
tool call contains its call ID, name, and decoded argument dictionary.

### `tools.py`

Contains ordinary functions for command execution, file operations, and the
session todo checklist. The explicit `TOOLS` dictionary associates each function
with the description and parameter schema shown to the model. `dispatch_tool`
calls the selected function and converts exceptions into text the model can use
to recover. Search rejects empty queries, skips common generated directories and
files larger than 1 MB, and caps each result at 100 matches. Every tool result
is capped at 50,000 characters before it enters model context. Foreground
commands have a fixed two-minute timeout. The `todo` tool replaces the full
process-local checklist on each call and enforces at most one `in_progress`
item.

## Context

Each model request contains only:

- The small system prompt in `agent.py`, including todo guidance for multi-step
  work.
- The current todo checklist when it is non-empty.
- The process-local conversation and tool history list.
- Tool definitions generated from the `TOOLS` dictionary.

The system prompt also tells the model the current working directory, configured
model, and that command execution uses Windows `cmd.exe`. It requires registered
tool names and non-empty parameters, and gives repository-overview tasks a
selective inspection strategy that avoids recursive trees, dependencies, tests,
Git state, and version archives unless requested.

There is no persistent session, automatic context trimming, repository
instruction loading, or long-term memory. Todo state shares the process lifetime
of conversation history and rolls back with failed or interrupted CLI turns.

## Tool Loop

1. The CLI appends a user message.
2. The agent sends the full history and tool definitions to the provider.
3. The parser extracts text and tool calls from the raw response.
4. If tools were requested, the agent executes each call in order.
5. Each result is appended with the matching call ID.
6. The agent calls the provider again.
7. A response without tool calls becomes the final answer.

The loop stops with an error after 20 model/tool steps and stops executing new
tools after 12 calls in one turn. These separate limits bound both repeated
model rounds and large parallel tool batches.
