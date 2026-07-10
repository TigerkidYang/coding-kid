# Versioning

## Purpose

Git records the implementation process, while browsable version directories
preserve complete teaching checkpoints. The project maintains both forms of
history.

## Living Implementation

The root project is the continuously evolving implementation:

```text
src/                 current source code
tests/               current tests
pyproject.toml       current project configuration
```

`main` is the central development line. The root implementation continues
forward after each completed version.

## Small Commits

Create a local commit after each coherent, verified increment. A commit should:

- Represent one understandable change.
- Avoid unrelated files.
- Include directly related tests and documentation.
- Use a short, descriptive message.
- Leave the affected work in a coherent state.

Do not commit every keystroke or arbitrary unfinished fragments. Do not delay
all work until one large end-of-version commit.

The agent is responsible for routine local Git management under these rules. It
must inspect the working tree before and after committing and preserve unrelated
user changes.

## Completed-Version Archives

Completed major versions are stored inside the repository:

```text
versions/
  NN-short-name/
    README.md
    src/
    tests/
    pyproject.toml
    ...other files required to run that version
```

Each archive contains the minimum complete project needed to understand, run,
and test that version. Copy relevant source, tests, dependency declarations,
lock files, configuration, prompts, and runtime assets when they are required.

Do not copy:

- `.git/` or other repository internals.
- Research repositories or reports.
- Article drafts.
- Secrets, local environment files, caches, logs, or generated output.
- Files unrelated to running or understanding the archived version.

Each archive `README.md` records:

- The version goal and scope.
- Its completion criteria or demonstrated capability.
- Setup, run, and test commands.
- The matching Git tag.

Archives are read-only historical teaching material. Current development must
not import from or depend on `versions/`.

## Naming

Use a two-digit sequence and a short lowercase hyphenated name:

```text
Directory: versions/NN-short-name/
Tag:       version-NN-short-name
```

Examples:

```text
versions/01-minimal-provider/
version-01-minimal-provider
```

Confirm the short name with the user when it is not already clear from the
version definition.

## Version-Completion Trigger

Run the archive procedure when the user explicitly indicates that:

- The current version or stage is complete.
- The project is ready to begin the next version or stage.

These statements authorize the normal local archive procedure. They do not
authorize a push, history rewrite, destructive cleanup, or changes unrelated to
the version transition.

## Archive Procedure

When a version-completion trigger occurs, the agent must:

1. Confirm the version number and short name if either is unclear.
2. Inspect `git status` and separate unrelated changes.
3. Verify the version against its recorded completion criteria.
4. Update tests, architecture, decisions, tasks, and user-facing instructions as
   required by the completed state.
5. Create any necessary final implementation commit.
6. Copy the runnable teaching checkpoint into `versions/NN-short-name/`.
7. Verify the archived copy independently where practical.
8. Add its `README.md` and commit the archive.
9. Create an annotated tag named `version-NN-short-name` on the archive commit.
10. Confirm that the tag and archive resolve to the intended version.
11. Continue future development from the root implementation on `main`.

The agent reports the resulting commits and tag to the user.

## Article References

Articles should link directly to files under `versions/NN-short-name/`. This
keeps historical code browsable without requiring readers to switch branches or
check out a tag.

The matching tag remains the authoritative Git checkpoint for recovery and
provenance.

## Correcting an Archived Version

Do not silently update a completed archive or move its published tag.

If the user explicitly requests a correction:

1. Keep the original tag unchanged.
2. Make the correction explicit in the archive history.
3. Create a corrective annotated tag such as
   `version-NN-short-name-fix1` when a new fixed checkpoint is required.
4. Create a maintenance branch only when ongoing work on that historical
   version is actually needed.

## Remote and Destructive Operations

Standing authorization covers:

- Read-only Git inspection.
- Staging related files.
- Routine local commits for coherent progress.
- Completed-version directory creation.
- Annotated version tags triggered by version completion.

Explicit user permission is still required for:

- Pushing commits or tags.
- Creating or publishing hosted releases.
- Rebasing or otherwise rewriting shared history.
- Deleting or moving branches and tags.
- Discarding changes or destructive cleanup.
