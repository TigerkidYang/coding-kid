# Decisions

This file records decisions that govern current and future work. Replace or
remove entries when they no longer describe the project.

## Use repository files as project memory

Decision:
Use `AGENTS.md` as the entry point and the files under `docs/` as durable project
memory.

Consequence:
Agents read the relevant memory before substantial work and keep it aligned with
the current project state.

## Build one complete version at a time

Decision:
The project is implementation-first. Define, implement, verify, and commit one
version before discussing the next one.

Consequence:
Do not maintain a multi-version roadmap or add speculative future capabilities
to current tasks and architecture.

## Define each version immediately before implementation

Decision:
The user decides each version's goal, scope, exclusions, and completion criteria
when that version is about to begin.

Consequence:
The first version is currently undefined. Agents may help the user think through
it but must not choose its contents in advance.

## Use research to support the current implementation

Decision:
Keep existing source-code research active as reference material and perform new
research when the current version raises a concrete question.

Consequence:
Research remains available throughout implementation but is not managed as an
independent parallel track.

## Keep implementation and authorship user-led

Decision:
The user is the sole implementer of project code and sole author of final
article text unless a specific task is explicitly delegated.

Consequence:
Agents research, explain, discuss, and perform requested operational work without
taking over implementation or authorship.

## Keep article work inactive

Decision:
Preserve existing article drafts without developing or publishing them while the
implementation is the active focus.

Consequence:
Article tasks and article-specific Git workflows do not appear in the active
project workflow. They resume only on explicit user direction.

## Keep a living main implementation and browsable version archives

Decision:
Use `main` for the continuously evolving root implementation. Preserve every
completed major version as an independently understandable and runnable copy
under `versions/NN-short-name/`, with a matching annotated tag named
`version-NN-short-name`.

Consequence:
Git commits retain the development history, while stable repository paths make
historical code easy to inspect, compare, and cite in teaching material. Archived
versions are read-only and must not become dependencies of current code.

## Delegate routine local version management to the agent

Decision:
The agent automatically creates coherent local commits during implementation
and performs the archive-and-tag procedure when the user declares a version
complete or begins the next one.

Consequence:
The user does not need to repeat these Git instructions in later chats. Pushes,
history rewrites, tag movement or deletion, and destructive cleanup still
require explicit permission. The complete policy is in `docs/VERSIONING.md`.
