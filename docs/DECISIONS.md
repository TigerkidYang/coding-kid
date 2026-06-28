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

