# Version 03 Context Assembly Evaluation

This paired goal-only slice measures the capability introduced by Version 03:
automatic, bounded loading of hierarchical project `AGENTS.md` instructions.
Version 02 and Version 03 receive the same tasks, model, and tool budget.

The runner creates disposable workspaces from `tasks.json`. Generated
workspaces are ignored. Raw reports and `SCORECARD.md` are kept as evaluation
evidence.

```powershell
uv run python evals/v03-context-assembly/run_context_slice.py --agent v02
uv run python evals/v03-context-assembly/run_context_slice.py --agent v03
uv run python evals/v03-context-assembly/run_context_slice.py --write-scorecard
```

Metrics:

- **Process:** Version 03's first provider request contains exactly the expected
  source-labeled project context and excludes forbidden instruction files.
- **Outcome:** `result.txt` contains the value required by the applicable
  project instructions.

Completion bar: Version 03 Process 6/6, Version 03 Outcome at least 5/6, and
Version 03 Outcome above Version 02.

