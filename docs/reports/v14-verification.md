# Version 14 Verification

Date: 2026-08-06

## Scope and Environment

Version 14 combines application-owned isolated Git worktrees for child Agents
with bounded Brave search and public-text fetch. Verification used the source
environment, Docker Desktop with `python:3.11-slim-bookworm`, and a clean Python
3.11 virtual environment installed from the built wheel.

No SWE-bench, paid batch, paid model request, or paid search request ran. The
process environment exposed neither `OPENROUTER_API_KEY` nor
`BRAVE_SEARCH_API_KEY`.

## Deterministic and Security Results

- The complete suite collected 421 tests: 420 passed and one Windows symlink
  test was skipped. Final runtime was 218.9 seconds.
- Ruff passed over the maintained `src` and `tests` trees. Repository-wide Ruff
  still reports nine pre-existing findings under frozen evaluation fixtures,
  which were not modified.
- Worktree tests cover dirty tracked and untracked baselines, concurrent
  isolation, child-only deltas, diff, integration, root conflicts, reconcile,
  rollback/retry, acceptance cleanup, explicit discard, restart orphaning,
  invalid ownership, and non-Git failure.
- Agent tests prove cwd-bound child tools and terminals, bounded visible context
  forks without reasoning/tool protocol, status projection, private failure and
  cancellation evidence, and parent-controlled integration.
- Web tests cover missing credentials, query/result bounds, numbered sources,
  redirect revalidation, loopback/private/mixed DNS, credentialed URLs,
  nonstandard ports, binary media, content encoding, response size, HTML text
  extraction, Plan/Review visibility, approval, and sandbox network denial.

## Stress and Lifecycle Results

Ten rounds each created four worktrees whose children modified the same tracked
path differently. All 40 deltas remained distinct, the root stayed unchanged,
and confirmed cleanup removed every Coding Kid worktree and branch.

Ten real Docker rounds each started an interactive shell, ran a same-container
workspace readiness check, exited, and closed its manager. Every matching
container was absent after its round. After the existing bounded PTY drain,
zero execution-session threads remained. An initial driver used a non-hex test
container token and was correctly rejected before launch; the corrected token
obeyed the runtime ID contract.

## Packaging and Installed Trials

The wheel at `output/v14-verification/coding_kid-0.1.0-py3-none-any.whl` is
862,434 bytes with 249 entries / 245 Python files. It contains the frozen V13
runtime plus living `web.py` and `worktrees.py`; it excludes tests, `showcase/`,
caches, bytecode, and logs.

A clean Python 3.11 environment installed the wheel and dependencies, then
launched V1-V14 from an unrelated Git project. All versions exited before any
provider request, and `--list-versions` identifies V14 as latest and default.
The first launch driver intentionally exposed that V14-only sandbox flags are
rejected for historical runtimes; the corrected per-version invocation passed.

Using only the installed package, a child edited a private worktree. The plain
CLI displayed its diff, integrated it into a new stage checkpoint, and
`/changes rollback` restored the root while returning the child workspace to
`ready`. A clean-installed Textual pilot rendered the V14 TUI and accepted
`/exit`.

Two outer ConPTY attempts reproduced the already-known nested full-screen input
timing limitation: one did not expose a title through pywinpty's read buffer and
one did not submit `/exit`. Both drivers terminated the child and left no
process. The installed Textual pilot is the deterministic TUI proof; ordinary
redirected installed CLI startup passed separately.

## Live Web Boundary

The direct installed `web_fetch("https://example.com/")` trial resolved the
hostname to `198.18.0.140`, part of the reserved benchmarking range rather than
a globally routable address. V14 rejected it before opening a socket. This is
the intended fail-closed SSRF behavior; weakening the address rule to fit the
verification host would invalidate the feature.

Because no Brave key was available, no fresh live search was attempted.
Deterministic transport tests exercised the complete request/response contract,
including fixed endpoint authentication without exposing the token. A future
credentialed smoke may be run only when the environment supplies a key.

## Outcome

All implementation, deterministic, security, stress, packaging, historical
runtime, installed CLI, and installed TUI criteria that do not require absent
credentials pass. The user confirmed stage completion on 2026-08-06.

The standalone archive at
`versions/14-isolated-collaboration-web-research/` independently collected 359
tests: 358 passed and one Windows symlink test skipped. Ruff lint passed, all 60
Python files pass format-check, and the 128,399-byte standalone wheel contains
34 entries without the cross-version launcher, historical runtimes, tests,
caches, or bytecode. A new Python 3.11 environment installed that wheel and
launched the V14 CLI successfully. The completed checkpoint uses annotated tag
`version-14-isolated-collaboration-web-research`.
