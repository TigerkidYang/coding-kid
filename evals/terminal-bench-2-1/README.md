# Terminal-Bench 2.1 evaluation

This directory contains the thin Harbor adapter used to evaluate the frozen
Coding Kid implementation on `terminal-bench/terminal-bench-2-1`.

The adapter installs a locally built wheel into each task container and runs one
non-interactive Version 14 turn with `gpt-5.6-luna` at `max` reasoning effort.
Secrets remain in process environment variables and must not be written here.

## Provider compatibility

Set these host environment variables before running Harbor:

- `CODING_KID_BENCH_API_KEY`: key for the OpenAI-compatible Responses API.
- `CODING_KID_BENCH_BASE_URL`: an endpoint reachable from task containers.
- `CODING_KID_BENCH_WHEEL`: absolute path to the frozen local wheel.

The current local proxy accepts `reasoning.effort=max` but rejects
`max_output_tokens`, so the adapter enables Coding Kid's compatibility switch.

## Network policy

Use the configured domestic Docker registry mirrors and a domestic PyPI index.
Inspect a task's `task.toml` and environment before pulling it. Do not start the
full dataset until every environment has been prefetched or otherwise shown not
to consume overseas proxy traffic.

## One-task smoke

`terminal-bench/fix-git` is the initial smoke task. It uses a small
`python:3.13-slim-bookworm` environment with Git and no GPU or model weights.
Run it with one attempt and one concurrent container before any broader eval.

## Verified smoke result

On 2026-08-06, Coding Kid completed one official `fix-git` trial with
`gpt-5.6-luna` and `reasoning.effort=max`:

- Harbor 0.9.0, one attempt, one concurrent Docker container.
- Task checksum:
  `d3220d70bc668ec6f4034fab51e62873dff724a61f824d764fd201d6f5e7a88a`.
- Reward: `1.0`; exceptions: `0`; retries: `0`.
- Agent execution: approximately 2 minutes 9 seconds.
- Total job runtime, including install and verification: approximately
  5 minutes 21 seconds.
- Harbor did not receive token or cost metadata from the compatible proxy.

The task image was pulled explicitly through
`docker.1ms.run/alexgshaw/fix-git:20260403`, then retagged to Harbor's expected
name. Both tags resolved to image digest
`sha256:389b9c8247610c2c5be080b1ac00429007c2c69bf57f7f26c79f0f75ba2d5c74`;
the local image size was 155,753,834 bytes. Python dependencies used the Aliyun
PyPI mirror. No benchmark expansion beyond this one valid trial was run.

## Resume

Harbor stores the job configuration and each trial result under the job
directory. Resume an interrupted full run without repeating completed trials:

```powershell
harbor job resume --job-path evals/terminal-bench-2-1/jobs/<job-name>
```

Use `--filter-error-type <ExceptionName>` only when deliberately retrying a
known infrastructure failure. Do not retry ordinary reward-zero trials.
