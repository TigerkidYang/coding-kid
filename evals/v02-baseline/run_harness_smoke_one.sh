#!/usr/bin/env bash
# Official harness for one already-cached instance (infrastructure smoke).
# Do not use this as the first check that mirrors work — run
# smoke_docker_mirror.py and prepull_swebench_images.py first.
set -euo pipefail
cd /work
python -m pip install -q -U pip swebench datasets
python -m swebench.harness.run_evaluation \
  --dataset_name SWE-bench/SWE-bench_Verified \
  --predictions_path /work/v2_verified_10_predictions_source.jsonl \
  --instance_ids pytest-dev__pytest-5809 \
  --max_workers 1 \
  --run_id coding_kid_v02_harness_smoke \
  --cache_level instance \
  --report_dir /work/harness_reports
