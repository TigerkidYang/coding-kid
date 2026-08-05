# Coding Kid Version 14 — Isolated Collaboration and Web Research

This teaching checkpoint gives child Agents independently reviewable Git
worktrees and adds bounded, attributable public Web research.

## Demonstrated Capability

- Writing children default to application-owned worktrees containing a stable
  snapshot of the root's tracked and non-ignored dirty state.
- A bounded context fork may include up to eight recent user/visible-assistant
  rounds, never tool protocol, outputs, hidden reasoning, or long-term memory.
- Child file tools, commands, interactive terminals, Skills, MCP, and Web tools
  use the child's effective cwd and retain their existing permission/sandbox
  boundary.
- Parent-controlled diff, reconcile, integrate, and confirmed discard actions
  preserve conflicts in isolation and never partially merge into the root.
- Integration enters the V12 stage checkpoint: rollback restores the root and
  retains retryable child work; acceptance cleans only validated application-
  owned worktrees and branches.
- `web_search` uses Brave's fixed endpoint and numbered source URLs.
  `web_fetch` performs GET-only public-text retrieval with pinned public-address
  connections, redirect revalidation, byte/text limits, and untrusted-content
  labels.
- Plan/Implementation/Review, Cautious/Auto/Full Access, immutable sandbox
  network policy, cancellation, CLI/TUI controls, and bounded parallelism govern
  both capabilities.

Version 14 does not add browser automation, JavaScript rendering, authenticated
browsing, arbitrary downloads, remote/nested Agents, non-Git isolation,
automatic root conflict resolution, or process/workspace reconnection.

## Verification

- Living implementation: 421 tests collected, 420 passed and one Windows
  symlink test skipped; Ruff passed over `src` and `tests`.
- Ten rounds of four overlapping worktrees preserved distinct child deltas,
  left the root unchanged, and removed all owned worktrees and branches.
- Ten real Docker interactive rounds passed same-container checks and left no
  containers or execution-session threads after bounded drain.
- The root wheel included frozen V13 plus living V14, and a clean Python 3.11
  install launched V1-V14 from an unrelated Git project.
- Installed CLI diff/integrate/checkpoint rollback and Textual TUI trials
  passed. No SWE-bench, paid batch, model request, or paid search ran.
- Live fetch correctly rejected the verification host's reserved `198.18/15`
  DNS mapping. Live Brave search was not attempted because no key was present.

See the root report `docs/reports/v14-verification.md` for complete evidence.

## Setup and Run

Requirements are Python 3.11+, uv, Docker plus a pre-pulled image for restricted
sandbox modes, and OpenRouter credentials for live model use. Set the optional
`BRAVE_SEARCH_API_KEY` environment variable to enable `web_search`.

```powershell
uv sync --extra dev
uv run coding-kid --sandbox danger-full-access --approval full-access
uv run coding-kid --sandbox workspace-write --sandbox-network
```

Use `/agents`, `/agent diff <id>`, `/agent integrate <id>`,
`/agent reconcile <id>`, `/agent discard <id> --confirm`, `/agent stop <id>`,
and `/changes` to inspect and govern collaboration directly.

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check src tests
uv run --extra dev ruff format --check src tests
```

The deterministic suite uses fake providers and fake Web transports. Docker
fixtures do not call OpenRouter or Brave.

## Git Checkpoint

Annotated tag: `version-14-isolated-collaboration-web-research`.
