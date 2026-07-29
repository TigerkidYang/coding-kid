# Eval Infrastructure Notes

## Todo discrimination slice (primary Todo evidence)

Goal-only multi-step tasks under `todo_slice/` measure Version 02 Todo vs
Version 01. Protocol: `TODO_SLICE.md`. Do **not** use Verified × 10 as Todo proof.

```text
uv run python evals/v02-baseline/todo_slice/bootstrap_fixtures.py
uv run python evals/v02-baseline/todo_slice/run_todo_slice.py --agent v01
uv run python evals/v02-baseline/todo_slice/run_todo_slice.py --agent v02 --only-v01-fails
```

## Rule: test before evaluation

Do not discover Docker/mirror/API problems during a full Verified × 10 harness
run. Use this order:

1. Unit tests: `uv run --extra dev pytest -q`
2. Live agent smoke (no SWE-bench): `uv run python evals/v02-baseline/smoke_todo_live.py`
3. Docker mirror smoke: `uv run python evals/v02-baseline/smoke_docker_mirror.py`
4. Pre-pull needed eval images via mirror + retag:
   `uv run python evals/v02-baseline/prepull_swebench_images.py`
5. Optional one-instance harness smoke (image already local):
   `run_harness_smoke_one.sh`
6. Only then: full Verified × 10 official harness

## Mirror strategy that works here

`registry-mirrors` alone is not enough for cold `swebench/sweb.eval.*` images.
Those pulls often 404 through the mirror fallback path.

Working path:

```text
docker pull docker.1ms.run/swebench/sweb.eval.x86_64.<image>:latest
docker tag  docker.1ms.run/swebench/sweb.eval.x86_64.<image>:latest \
            swebench/sweb.eval.x86_64.<image>:latest
```

`prepull_swebench_images.py` automates that for the Verified × 10 slice and
retries transient EOF / proxy blips. Keep `--cache_level instance` so later
harness runs reuse local images.

If Docker Desktop routes traffic through a local proxy (for example
`127.0.0.1:7890`), keep that proxy running during large pulls, or add the
domestic mirror hosts to Docker's no-proxy / bypass list so pulls do not depend
on the VPN process staying up.
