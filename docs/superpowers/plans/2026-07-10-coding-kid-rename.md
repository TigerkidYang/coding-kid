# Coding Kid Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt `Coding Kid` as the project identity across repository-controlled content and hosting metadata without changing its implementation scope or version state.

**Architecture:** Treat the rename as a documentation and naming migration because the repository has no implementation yet. Use `Coding Kid` for the product name, `coding-kid` for repository and distribution identifiers, and `coding_kid` for the future Python import package.

**Tech Stack:** Markdown, Git, Python naming conventions

## Global Constraints

- Preserve the current one-version-at-a-time workflow and keep the first version undefined.
- Preserve user-authored article prose except for direct project-name and package-path references.
- Do not rename generic references to the broader “Coding Agent” software category.
- Rename the hosted GitHub repository only after confirming administrator access and target-name availability.

---

### Task 1: Establish the project identity

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/PROJECT_CONTEXT.md`
- Modify: `docs/DECISIONS.md`
- Modify: `docs/TASKS.md`
- Modify: `docs/CONTENT_STRATEGY.md`

**Interfaces:**
- Consumes: The user-selected display name `Coding Kid`.
- Produces: A single naming convention for future documentation and implementation.

- [x] **Step 1: Update the project goal and current-state memory**

Record `Coding Kid` as the product name while retaining “Python coding agent” as its description.

- [x] **Step 2: Record identifier conventions**

Add a decision defining `Coding Kid`, `coding-kid`, and `coding_kid` as the display, repository/distribution, and Python package forms.

- [x] **Step 3: Verify memory consistency**

Run: `rg -n -e "Coding Kid" -e "coding-kid" -e "coding_kid" AGENTS.md docs`

Expected: The new name and identifier forms appear only in intentional project-identity contexts.

### Task 2: Update preserved article references

**Files:**
- Rename: `docs/articles/01-coding-agent-from-scratch-en.md` to `docs/articles/01-coding-kid-from-scratch-en.md`
- Rename: `docs/articles/01-coding-agent-from-scratch-zh.md` to `docs/articles/01-coding-kid-from-scratch-zh.md`

**Interfaces:**
- Consumes: The naming convention from Task 1.
- Produces: Brand-aligned article filenames, titles, and future source-path examples.

- [x] **Step 1: Rename the article files**

Use `coding-kid` in the filenames.

- [x] **Step 2: Update direct brand references only**

Use `Coding Kid` in titles and `src/coding_kid/provider.py` in the Python package-path example. Leave all other user-authored prose unchanged.

- [x] **Step 3: Verify preserved content**

Run: `Get-Content docs/articles/01-coding-kid-from-scratch-zh.md -TotalCount 25`

Expected: The article remains present and its direct brand references use the new naming convention.

### Task 3: Verify and commit the repository rename

**Files:**
- Inspect: all repository-controlled files
- Inspect: `.git/config`

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces: A clean content-level rename and a clear report of host-level items that remain external.

- [x] **Step 1: Scan for legacy names**

Run: `$legacy = 'mini' + 'code'; rg -n --hidden -g '!.git/**' -i -e $legacy .`

Expected: No matches in repository-controlled content.

- [x] **Step 2: Inspect changes and repository state**

Run: `git diff --check` and `git status --short --branch`

Expected: No whitespace errors; only rename-related files are modified or newly added, while pre-existing untracked article drafts remain clearly identifiable.

- [x] **Step 3: Commit tracked rename changes**

Stage only tracked project-memory changes and this plan, excluding pre-existing untracked article drafts unless the user explicitly requests adding them to Git.

Run: `git commit -m "docs: rename project to Coding Kid"`

Expected: A local commit containing only the tracked repository rename.

- [x] **Step 4: Rename and verify the hosted repository**

Run: `gh repo rename coding-kid --repo TigerkidYang/<current-name> --yes`

Expected: GitHub reports the repository as `TigerkidYang/coding-kid`; update
`origin` to the canonical URL if Git does not do so automatically.
