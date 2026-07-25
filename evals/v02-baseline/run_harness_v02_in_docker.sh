#!/usr/bin/env bash
set -euo pipefail
cd /work
python -m pip install -q -U pip swebench datasets
IDS=(
  astropy__astropy-12907
  django__django-15278
  matplotlib__matplotlib-13989
  psf__requests-5414
  pydata__xarray-2905
  pylint-dev__pylint-4970
  pytest-dev__pytest-5809
  scikit-learn__scikit-learn-15100
  sphinx-doc__sphinx-8269
  sympy__sympy-20590
)
# Keep instance images cached so later runs do not re-download multi-GB layers.
python -m swebench.harness.run_evaluation \
  --dataset_name SWE-bench/SWE-bench_Verified \
  --predictions_path /work/v2_verified_10_predictions_source.jsonl \
  --instance_ids "${IDS[@]}" \
  --max_workers 1 \
  --run_id coding_kid_v02_verified10 \
  --cache_level instance \
  --report_dir /work/harness_reports
