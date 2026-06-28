# Research

Use this file to track source-code reading and comparisons of existing agent
projects.

## Purpose

The user will study strong open-source SWE Agent / Coding Agent projects to
understand their design and implementation details.

Research notes should support two outcomes:

- Better implementation decisions for this repository.
- Better explanations for the teaching article series.

## Research Topic List

### Core Agent Capabilities

- Agent core loop:
  - Task scheduling and task decomposition.
  - Loop and workflow control.
  - Large input prompt assembly.
  - Output parser.
  - Executor.
- Agent tool calling:
  - Terminal command execution.
  - Terminal output reading.
  - Basic file I/O, including read, write, and search.
  - Minimum SWE Agent tool set.

### Advanced Agent Capabilities

- How to implement long-term memory.
- How to implement multi-agent workflows.
- How to manage background tasks.
- How to implement skills and plugins as pluggable context.
- How to implement context auto-compression.
- How to better control the whole loop and workflow.
- How to control the sandbox environment.
- How to design freely configurable MCP support.
- How to initially implement visualization and observability:
  - What should be shown to users.
  - How to design a more suitable terminal UI.

## Suggested Note Format

```markdown
## Project name

Repository:
Link or local path.

Why study it:
What this project can teach us.

Key ideas:
- ...

Implementation details:
- ...

Questions:
- ...

Useful takeaways:
- ...
```

## Candidates

### First Parallel Study Set

## Claude Code source archive

Repository:
https://github.com/yasasbanukaofficial/claude-code

Local path:
`research/repos/claude-code`

Snapshot:
- Stars checked on 2026-06-29: 3612.
- Default branch: `main`.
- Local HEAD: `a371abb`.

Why study it:
Use this repository to study Claude Code's extracted implementation shape and
compare it with Codex. Focus especially on agent loop, tool calling, prompt
assembly, permission flow, and terminal/file interaction.

Questions:
- How is the main loop organized?
- How are tools represented and dispatched?
- How is context assembled and compressed?
- How are terminal commands and file edits handled?
- Which parts are product workflow, and which parts are core agent mechanics?

## OpenAI Codex

Repository:
https://github.com/openai/codex

Local path:
`research/repos/codex`

Snapshot:
- Stars checked on 2026-06-29: 94189.
- Default branch: `main`.
- Local HEAD: `bdd282f`.

Why study it:
Use Codex as the main open-source reference for a modern terminal coding agent.
Focus on architecture, sandboxing, approval flow, tool execution, patch/edit
workflow, CLI design, and how the agent turns user intent into repository
changes.

Questions:
- Where is the core agent loop implemented?
- How are model calls, tools, approvals, and sandboxing connected?
- How does Codex represent file edits and patches?
- How does Codex keep terminal UI, task state, and execution state synchronized?
- Which architectural ideas should be adapted into the Python implementation?
