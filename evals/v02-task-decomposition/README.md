# Version 02 feature evaluation

This directory contains a paired, feature-specific SWE-bench Verified
evaluation for Version 02 task decomposition.

Read:

- `PROTOCOL.md` for controls and the predeclared success rule.
- `SCORECARD.md` for the completed result and interpretation.
- `final_10_ids.json` for the frozen final instances and selection rule.

## Run order

1. Prepare and verify every official instance image through the domestic
   registry:

   ```powershell
   .\.venv\Scripts\python.exe evals\v02-task-decomposition\docker_images.py `
     --ids-file evals\v02-task-decomposition\final_10_ids.json
   ```

2. Run paired inference:

   ```powershell
   .\.venv\Scripts\python.exe evals\v02-task-decomposition\run_inference.py `
     --agent v01 --run-name final10 `
     --ids-file evals\v02-task-decomposition\final_10_ids.json

   .\.venv\Scripts\python.exe evals\v02-task-decomposition\run_inference.py `
     --agent v02 --run-name final10 `
     --ids-file evals\v02-task-decomposition\final_10_ids.json
   ```

3. Grade both prediction JSONL files with the official SWE-bench Docker
   harness. Keep `--cache_level instance` and confirm the harness reports that
   all ten local instance images are reused.

Inference outputs, workspaces, and complete harness logs are local artifacts
and are ignored by Git. The frozen IDs, scripts, protocol, scorecard, and final
official summary reports are durable evidence.
