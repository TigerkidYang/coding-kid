# Version 11 Live Verification

Date: 2026-08-05

## Artifact and Environment

- Artifact: `dist/coding_kid-0.1.0-py3-none-any.whl`
- Clean runtime: a temporary Python virtual environment
- Restricted backend: Docker Desktop 28.4.0
- Image: `python:3.11-slim-bookworm`
- Image digest observed during verification:
  `sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3`
- Model: `openai/gpt-5.6-luna`
- Interface: installed Version 11 full-screen Textual TUI driven through a
  Windows pseudo-terminal

No SWE-bench run or paid batch evaluation was authorized or performed.

## Deterministic and Packaging Results

- Pytest: 309 passed in 109.37 seconds.
- Ruff lint and format checks: passed.
- Wheel: 166 entries / 162 Python files, including the frozen V10 runtime and
  living V11. It contains no tests, evaluations, `showcase/`, caches, or
  bytecode.
- Clean install: explicit V1-V11 and default V11 all launched from an unrelated
  project directory without a provider request.

## Docker Isolation and Cleanup

A disposable project demonstrated a UTF-8 workspace write (`沙箱-ok`) while a
host sibling secret was not mounted. `.git/config` was read-only, the host
`OPENROUTER_API_KEY` marker was absent, default network DNS failed, and the
same write failed under `read-only`. An explicitly network-enabled read-only
runtime reached `https://example.com` with HTTP 200.

Ten rounds combined a timed-out foreground `sleep` with an immediately stopped
background container. The first run found a real registration race: cleanup
could issue `docker rm` before `docker run` registered its name, then kill the
client while the daemon completed container creation. Termination was changed
to stop the client first and perform bounded removal retries. The repeated run
passed 10/10 rounds with zero labeled containers left.

## Real TUI Scenarios

### Default workspace-write

The model wrote and read `result.txt` containing exactly `沙箱成功-V11`. A
built-in read of an absolute sibling path returned `SandboxViolation`; writing
`.git/blocked.txt` returned the protected-metadata denial. A container command
printed `ABSENT` for a host-only `CK_HOST_SECRET`, and urllib failed with DNS
resolution disabled. The sibling secret was unchanged and no metadata file was
created. The final TUI answer ended with `V11_WORKSPACE_TRIAL_COMPLETE`.

### Read-only

In a fresh installed-wheel TUI, a built-in `write` of `ro-tool.txt` was denied.
The model then attempted POSIX shell redirection to `ro-shell.txt` inside the
container; the read-only project mount denied it as well. Neither file existed
after the session, whose final answer ended with
`V11_READONLY_TRIAL_COMPLETE`.

### Explicit danger-full-access

A third installed-wheel TUI used no provider request. `/sandbox` visibly
reported `danger-full-access`, `Backend: host`, and `Network: host`, then the
session exited normally. This confirms the compatibility mode is explicit in
the interface rather than presented as restricted isolation.

## Usage Bound

The workspace-write transcript contains eight model responses and the
read-only transcript contains three, for 11 paid responses total. Their final
recorded input snapshots were 3,155 and 1,649 tokens. Coding Kid does not
persist exact provider cost, so no false precision is claimed; based on these
short bounded trials, task-wide spend is conservatively below USD 0.05 and well
inside the standing USD 1.00 allowance.

## Outcome

All Version 11 implementation completion criteria passed. The root
implementation remains unarchived until the user explicitly confirms stage
completion, at which point the normal archive, annotated-tag, and push procedure
applies.
