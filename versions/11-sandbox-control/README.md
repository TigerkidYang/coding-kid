# Coding Kid Version 11 — Sandbox Control

This teaching checkpoint places one explicit, fail-closed sandbox policy around
model-controlled local file and process effects while preserving Version 10's
synchronous Turn/Step runtime.

## Demonstrated Capability

- Startup selects `read-only`, default `workspace-write`, or explicit
  `danger-full-access` for the entire application lifetime.
- Restricted foreground commands, background tasks, and child Agents execute in
  hardened Docker containers with bounded resources, a filtered environment,
  and network disabled by default.
- Built-in read, search, write, patch, and delete tools share one canonical
  project-root policy that rejects traversal, link escape, read-only mutation,
  and writes to `.git` or `.coding-kid`.
- Restricted startup fails if Docker or the configured image is unavailable;
  tool denial never triggers a host retry or policy elevation.
- MCP processes and tools are withheld in restricted modes because their local
  or remote effects cannot be contained by this Docker boundary. Inert Skills
  remain available.
- CLI and TUI status expose the effective mode, backend, project root, image,
  and network state. `danger-full-access` is visibly identified as host access.
- Timeout, cancellation, task/Agent stop, and shutdown use named-container
  removal with bounded retry across the Docker registration race.

Version 11 does not add per-command approvals, remembered permissions,
model-requested escalation, automatic unsandboxed retry, domain-level network
proxies, image construction, VM lifecycle, or protection from a compromised
Docker daemon or container kernel escape.

## Verification

- Root implementation: **309 deterministic tests** plus Ruff lint and format
  checks.
- Standalone archive: **259 deterministic tests** plus Ruff lint and format
  checks. Launcher-selection tests are omitted because this checkpoint starts
  V11 directly.
- Real Docker isolation probes passed Unicode workspace writes, external-path
  and metadata denial, host-secret filtering, default network denial, explicit
  network access, and read-only enforcement.
- Ten rounds of foreground timeout plus immediate background stop passed with
  zero labeled containers left after a discovered container-registration race
  was fixed.
- The root wheel contained 166 files / 162 Python files and launched V1–V11 plus
  default V11 from a clean unrelated directory.
- Real installed-wheel `openai/gpt-5.6-luna` TUI trials passed
  `workspace-write`, `read-only`, and `danger-full-access` behavior in 11 paid
  responses, conservatively below USD 0.05. No SWE-bench or paid batch
  evaluation was run.

## Setup

Requirements:

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Docker plus a pre-pulled sandbox image for restricted modes
- `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` for live use

```powershell
uv sync --extra dev
docker pull python:3.11-slim-bookworm
```

## Run

Start standalone Version 11 in the project it should operate on:

```powershell
uv run coding-kid
uv run coding-kid --sandbox read-only
uv run coding-kid --sandbox workspace-write --sandbox-network
uv run coding-kid --sandbox danger-full-access
```

Session selection supports `--new`, `--continue`, `--resume`,
`--list-sessions`, and `--delete-session`. Use `/sandbox` in the CLI or TUI to
inspect the effective policy.

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

The maintained deterministic tests use fake providers. MCP fixture tests start
only local test servers; they do not call OpenRouter.

## Git Checkpoint

Annotated tag: `version-11-sandbox-control`.
