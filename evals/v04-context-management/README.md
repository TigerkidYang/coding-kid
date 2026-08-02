# Version 04 Context-Management Evaluation

This focused evaluation compares the archived Version 03 runtime with the
living Version 04 runtime on three long-conversation fixtures:

1. preserving a corrected user intent;
2. preserving evidence returned by a tool-shaped protocol round;
3. remaining useful after two consecutive compactions.

It then drives the real Version 04 terminal loop in a temporary project. The
model must read three padded evidence files, compact in the middle of the tool
loop, create the requested result, and report completion.

The runner is deliberately bounded. It accepts only `openai/gpt-5.6-luna`,
counts every Responses API request (including summaries), and raises before a
31st request. It does not run SWE-bench or any other broad benchmark.

Run it only with fresh spending authorization:

```powershell
$env:OPENROUTER_API_KEY = [Environment]::GetEnvironmentVariable(
  "OPENROUTER_API_KEY", "User"
)
$env:OPENROUTER_MODEL = "openai/gpt-5.6-luna"
uv run python evals/v04-context-management/run_context_management_slice.py
```

Generated reports are `v03_report.json`, `v04_report.json`,
`cli_smoke_report.json`, and `SCORECARD.md`. Temporary workspaces are ignored.
