# Tasks

## Current Version

No version is currently defined.

## Next Action

- Discuss and define the first version when the user is ready.
- Record its goal, included scope, excluded scope, and completion criteria before
  implementation begins.

## Current Constraints

- Do not define later versions.
- Do not implement project code until the user has defined the current version
  or explicitly delegates a concrete implementation task.
- Research only as needed to answer questions raised by the current version.
- Do not work on articles unless the user explicitly resumes article work.
- Follow `docs/VERSIONING.md` for routine commits and completed-version
  archives.

## Established Project Operations

- `main` holds the continuously evolving implementation.
- Coherent, verified increments receive small local commits.
- A user-declared version completion or transition triggers an archive under
  `versions/` and a matching annotated Git tag.
- The agent performs this local Git maintenance automatically within the limits
  defined in `docs/VERSIONING.md`.

## Available Research

- General research notes: `docs/RESEARCH.md`.
- Claude Code source reports: `docs/reports/claude-code-source-report.md` and its
  Chinese version.
- Codex source reports: `docs/reports/codex-source-report.md` and its Chinese
  version.
- Claude Code and Codex comparison reports under `docs/reports/`.
