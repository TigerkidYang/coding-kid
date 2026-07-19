# Architecture

## Overview

Version 01 is a synchronous terminal coding agent. It deliberately uses small
functions and plain Python data structures so the complete workflow remains
visible.

```text
cli.py
  -> agent.py
       -> provider.py
       -> parser.py
       -> tools.py
```

## Modules

### `cli.py`

Owns the outer conversation loop. It reads terminal input, appends user
messages to one in-memory list, shows tool activity, and prints the final model
answer.

### `agent.py`

Owns the inner agent loop. It sends the current context to the provider, keeps
the raw model output in history, executes requested tools sequentially, appends
their results, and repeats until the model returns no more tool calls.

### `provider.py`

Makes one non-streaming OpenAI request and returns the raw response. It does not
parse output, manage history, execute tools, or abstract other model vendors.

### `parser.py`

Extracts assistant text and function calls from one provider response. A parsed
tool call contains its call ID, name, and decoded argument dictionary.

### `tools.py`

Contains ordinary functions for command execution and file operations. The
explicit `TOOLS` dictionary associates each function with the description and
parameter schema shown to the model. `dispatch_tool` calls the selected function
and converts exceptions into text the model can use to recover.

## Context

Each model request contains only:

- The small system prompt in `agent.py`.
- The process-local conversation and tool history list.
- Tool definitions generated from the `TOOLS` dictionary.

There is no persistent session, automatic context trimming, repository
instruction loading, or long-term memory.

## Tool Loop

1. The CLI appends a user message.
2. The agent sends the full history and tool definitions to the provider.
3. The parser extracts text and tool calls from the raw response.
4. If tools were requested, the agent executes each call in order.
5. Each result is appended with the matching call ID.
6. The agent calls the provider again.
7. A response without tool calls becomes the final answer.

The loop stops with an error after 20 model/tool steps to avoid an accidental
infinite loop.
