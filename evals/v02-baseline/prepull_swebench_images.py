"""Pre-pull SWE-bench eval images through a domestic mirror and retag them.

Harness expects official Docker Hub names such as:

  swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-5809:latest

Public registry-mirrors alone often 404 on these cold images. Explicit prefix
pulls through docker.1ms.run, then retagging, is the reliable path.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
INSTANCES_PATH = BASE / "verified_10_instances.json"
DEFAULT_MIRROR = "docker.1ms.run"


def instance_image(instance_id: str) -> str:
    # swebench harness naming: owner__name-123 -> owner_1776_name-123
    return f"swebench/sweb.eval.x86_64.{instance_id.replace('__', '_1776_')}:latest"


def run(cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def exists(name: str) -> bool:
    return run(["docker", "image", "inspect", name], timeout=60).returncode == 0


def pull_and_retag(mirror: str, official: str) -> None:
    mirrored = f"{mirror}/{official}"
    if exists(official):
        print(f"SKIP {official} (already local)")
        return
    if not exists(mirrored):
        print(f"PULL {mirrored}")
        started = time.perf_counter()
        result = run(["docker", "pull", mirrored], timeout=7200)
        elapsed = time.perf_counter() - started
        if result.returncode != 0:
            detail = (result.stderr or result.stdout)[-1500:]
            raise RuntimeError(f"pull failed ({elapsed:.1f}s): {detail}")
        print(f"OK   pulled in {elapsed:.1f}s")
    print(f"TAG  {mirrored} -> {official}")
    result = run(["docker", "tag", mirrored, official], timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mirror", default=DEFAULT_MIRROR)
    parser.add_argument(
        "--instance-id",
        action="append",
        dest="instance_ids",
        help="Pull only these instance IDs (repeatable). Default: all verified_10.",
    )
    args = parser.parse_args()

    instances = json.loads(INSTANCES_PATH.read_text(encoding="utf-8"))
    ids = args.instance_ids or [item["instance_id"] for item in instances]

    failures: list[str] = []
    for instance_id in ids:
        official = instance_image(instance_id)
        try:
            pull_and_retag(args.mirror, official)
            print(f"PASS {instance_id}")
        except Exception as error:
            failures.append(f"{instance_id}: {error}")
            print(f"FAIL {instance_id}: {error}", file=sys.stderr)

    if failures:
        print(f"Failed {len(failures)}/{len(ids)} image pulls", file=sys.stderr)
        return 1
    print(f"All {len(ids)} images ready for harness")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
