# Decisions

Record durable project decisions here. Use this format:

```markdown
## YYYY-MM-DD - Decision title

Context:
What problem or constraint led to this decision.

Decision:
What was decided.

Consequence:
What this means for future work.
```

## 2026-06-29 - Use repository files as AI project memory

Context:
The project will be rebuilt from scratch, and future work may happen across many
separate AI-agent chats.

Decision:
Use `AGENTS.md` as the agent entry point and `docs/` files as durable project
memory.

Consequence:
Future agents should read `AGENTS.md` first, then the relevant files under
`docs/`, before making non-trivial changes.

## 2026-06-29 - Build a Python SWE Agent as a learning and teaching project

Context:
The user wants to rebuild the repository around a long-term project that combines
deep technical learning, from-scratch implementation, and public teaching content.

Decision:
The project direction is to hand-write a Python SWE Agent / Coding Agent from
scratch, while also studying strong open-source agent projects and publishing a
series of educational articles on GitHub and X.

Consequence:
Future work should treat implementation, research notes, and article drafts as
parallel first-class tracks. The agent should start with an MVP but be designed
to evolve toward a modern engineering-grade system.
