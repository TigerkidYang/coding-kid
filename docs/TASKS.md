# Tasks

## Current Core Version: 14 — Isolated Collaboration and Web Research

Completion status: complete. The user confirmed stage completion on 2026-08-06.
The standalone checkpoint is archived under
`versions/14-isolated-collaboration-web-research/` with annotated tag
`version-14-isolated-collaboration-web-research`. No SWE-bench, paid batch, or
paid model request ran.

### Goal

Let child Agents develop in independently reviewable Git worktrees and return
only their own changes through a parent-governed integration workflow, while
adding bounded, attributable Web search and fetch tools under the existing
workflow, approval, and network policies.

### Included Scope

- Application-owned Git worktrees that preserve the root's initial dirty state
  as a private baseline and isolate each child's later delta.
- Explicit bounded parent-context forks, cwd-bound child commands and terminals,
  durable workspace manifests, diff, reconcile, integrate, and discard actions.
- V12 checkpoint-aware integration: rollback restores pending work and acceptance
  finalizes workspace cleanup.
- Bounded Brave Web Search plus public-text Web fetch with source attribution,
  external-content labeling, public-address validation, pinned connections, and
  safe redirects.
- Plan/Implementation/Review, Cautious/Auto/Full Access, all sandbox modes,
  CLI/TUI state, child ownership, cancellation, and bounded parallelism.
- Frozen V13 runtime plus installed V1-V14 selection.

### Excluded Scope

- Browser/GUI automation, JavaScript rendering, screenshots, forms, uploads,
  cookies, authenticated URLs, binary/PDF persistence, or arbitrary downloads.
- Remote or nested Agents, custom VCS hooks, non-Git workspace isolation, or
  persistent child conversations.
- Automatic changes to a conflicted root worktree, automatic merge commits,
  autonomous model wake-up, or a new benchmark.

### Completion Criteria

- Concurrent Agents can edit overlapping paths without seeing each other's
  unintegrated changes or changing the root worktree.
- A dirty root snapshot is visible to children, but integration applies only the
  child's delta and remains reversible through the V12 stage checkpoint.
- Conflicts are reproduced and resolved inside isolation; restart preserves
  unfinished workspace evidence; cleanup never touches unowned Git state.
- Search returns fresh titled URLs/snippets and fetch returns bounded readable
  text with continuation; both obey approval, network, SSRF, cancellation,
  external-content, and source-attribution rules.
- Pytest, Ruff, ten worktree and Docker stress rounds, wheel inspection, V13
  fidelity, clean-install V1-V14 launches, and direct installed terminal/TUI
  trials pass within the authorized live-spend boundary.

### Implementation Sequence

1. Freeze V13, advance the launcher, and record the V14 boundary.
2. Build the worktree lifecycle, dirty snapshot baseline, cwd-bound execution,
   persistence, and safe cleanup.
3. Add context forks and parent-controlled diff/reconcile/integrate/discard
   operations with workflow/checkpoint and CLI/TUI integration.
4. Add the secure Web runtime, tools, permissions, UI, and child integration.
5. Complete deterministic, security, stress, packaging, installed-terminal, and
   bounded live-model verification; update durable documentation.

### Verification Result

- 421 tests collected: 420 passed and one Windows symlink test skipped; Ruff
  passes over `src` and `tests`.
- Ten rounds of four overlapping isolated worktrees preserved the unchanged
  root and removed all application-owned worktrees and branches.
- Ten real Docker interactive rounds passed same-container readiness checks and
  left no containers or execution-session threads after bounded drain.
- The 862,434-byte wheel contains 249 entries / 245 Python files, including the
  frozen V13 runtime and living V14 modules, without tests, showcase, cache, or
  bytecode.
- A clean Python 3.11 installation launched V1-V14 from an unrelated Git
  project. Installed-wheel CLI diff/integrate/checkpoint rollback and a Textual
  TUI `/exit` pilot passed.
- Deterministic Web security tests cover Brave results, attribution, redirects,
  DNS and URL SSRF cases, content types, encodings, and size limits. Live Brave
  search was unavailable because no key was present; host DNS maps public names
  to reserved `198.18/15`, which the real fetch correctly rejected.

See `docs/reports/v14-verification.md` for the complete evidence.

The standalone archive independently passes 358 of 359 tests with one Windows
symlink skip, Ruff lint, format-check over 60 Python files, wheel inspection,
and clean Python 3.11 installation/startup.
