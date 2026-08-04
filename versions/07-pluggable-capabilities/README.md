# Coding Kid Version 07 — Pluggable Capabilities

This teaching checkpoint adds a session-scoped capability runtime to Version
06's persistent coding agent. Skills provide on-demand instructions, MCP
servers provide structured tools, and explicitly enabled local Plugins package
and namespace both.

## Demonstrated Capability

- Discovers user, hierarchical project, and Plugin `SKILL.md` files with
  deterministic precedence and bounded metadata.
- Loads complete Skill bodies only after `$skill` or model `skill(name)`
  invocation, with an eight-Skill per-turn limit.
- Strictly reads executable configuration only from the user-owned
  `%CODING_KID_HOME%/capabilities.json`.
- Rejects Plugin path and symlink escape while preserving `plugin:skill` and
  `mcp__plugin__server__tool` source namespaces.
- Connects official MCP Python SDK clients over stdio or Streamable HTTP on a
  dedicated asyncio thread while the Agent loop remains synchronous.
- Filters, normalizes, bounds, times out, cancels, and closes MCP tools and
  transports before exposing them through one session `ToolRegistry`.
- Reports capability summaries and redacted failures in the plain CLI and TUI
  through `/capabilities` and source-aware activity records.

The checkpoint passed 213 deterministic tests, Ruff lint and format checks,
wheel inspection, and fresh-install V1–V7 launches. One minimal real
`openai/gpt-5.6-luna` session loaded the example Plugin Skill, called its
read-only MCP tool, and returned independently verified file measurements. No
SWE-bench or paid batch evaluation was run.

## Setup

Requirements:

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` for live use

```powershell
uv sync --extra dev
```

## Run

Start Coding Kid inside the project it should operate on:

```powershell
uv run coding-kid
```

This standalone archive starts V07 directly and retains the Version 06 session
flags. Capability configuration lives at
`%CODING_KID_HOME%/capabilities.json`; `/capabilities` shows its active snapshot.
The disabled example under `examples/plugins/readonly-inspector/` demonstrates
one Skill guiding the Agent to one read-only Plugin MCP tool.

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

The tests use local MCP servers and fake model providers except for the
separately recorded minimal live verification.

## Intentional Limits

Version 07 does not provide a sandbox, approval workflow, Plugin marketplace,
download/update/signing, OAuth, credential storage, MCP Resources or Prompts,
dynamic tool refresh, background reconnect, Hooks, Apps, LSP, multi-agent work,
or generic background tasks. Built-in and MCP tools inherit the current user's
permissions.

The cross-version launcher remains an unnumbered root-project facility. This
archive does not recursively carry the V1–V6 bundled runtimes.

## Git Checkpoint

Annotated tag: `version-07-pluggable-capabilities`.
