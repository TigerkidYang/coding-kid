# Project Context

## Current Purpose

This repository is being rebuilt from scratch as a hands-on SWE Agent / Coding
Agent project.

The project has three parallel tracks:

- Learning and exploration: study strong open-source agent products and explain
  their implementation details through guided code reading.
- From-scratch implementation: hand-write a Python agent step by step, starting
  with an MVP and iterating toward a more modern engineering-grade system.
- Teaching content creation: turn the learning and implementation process into a
  series of educational articles for GitHub and X Articles.

The deeper purpose is not only to ship an MVP. The project should help the user
thoroughly understand agent internals, produce teaching material that clarifies
that understanding, and become a portfolio artifact that demonstrates depth in
SWE agent engineering.

## Product Scope

The target product is a Python SWE Agent / Coding Agent built from scratch.

Expected long-term capabilities may include:

- Understanding a repository and maintaining project memory.
- Planning and executing coding tasks.
- Reading, editing, and testing code.
- Using tools safely.
- Iterating on itself over time.
- Approaching the shape of a modern engineering product rather than remaining a
  toy demo.

The first implementation target should still be a small MVP.

## Collaboration Model

The user is the project lead. The AI assistant supports the user in three roles:

- Tutor: answer questions, explain logic, implementation details, and source
  code while the user learns and writes code by hand.
- Drafter: turn the user's detailed explanations and teaching direction into
  article drafts.
- Text editor: directly edit Markdown files in the repository, and when needed,
  help edit X Articles through the user's browser tooling.

## Working Preference

The user wants to work in separate chats, each focused on a specific part of the
project. Each chat should be able to reconstruct the important project context by
reading versioned files.

The memory system should stay practical:

- Store stable project knowledge.
- Keep notes short and factual.
- Update memory when decisions or architecture change.
- Avoid duplicating details that are obvious from source code.

Because the project spans code, research, and writing, future agents should keep
these tracks connected but separately documented.
