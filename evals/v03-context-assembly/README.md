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

Recorded result:

- Version 02 outcome: **4/6**
- Version 03 process: **6/6**
- Version 03 outcome: **6/6**

## SWE-bench Verified × 10

The same ten-instance secondary regression slice used for Version 02 was run
with the official SWE-bench harness. The tracked prediction file and official
summary report make the run reproducible:

```powershell
uv run python evals/v02-task-decomposition/run_inference.py `
  --agent v03 `
  --ids-file evals/v03-context-assembly/verified_10_ids.json `
  --run-name v03_verified10

docker run --rm `
  -v /var/run/docker.sock:/var/run/docker.sock `
  -v "${PWD}/evals/v03-context-assembly:/work" `
  python:3.11 bash /work/run_verified_harness.sh
```

Official result: **7/10 resolved**, 10/10 completed, 0 empty patches, and
0 harness errors. This exceeds the existing 5/10 regression threshold.
