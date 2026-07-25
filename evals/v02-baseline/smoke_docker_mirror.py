"""Smoke-test domestic Docker Hub mirrors before any SWE-bench harness run.

This is infrastructure validation, not agent evaluation.

Exit codes:
  0 — mirrors and retag path are usable
  1 — a required check failed
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_MIRROR = "docker.1ms.run"
ALPINE_REF = "library/alpine:3.20"
# One real SWE-bench Verified eval image from our V02 slice (~3.6GB).
SWEB_IMAGE = "swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-5809:latest"


def run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def image_exists(name: str) -> bool:
    result = run(["docker", "image", "inspect", name], timeout=60)
    return result.returncode == 0


def pull(name: str, timeout: int = 1800) -> None:
    print(f"PULL {name}")
    started = time.perf_counter()
    result = run(["docker", "pull", name], timeout=timeout)
    elapsed = time.perf_counter() - started
    if result.returncode != 0:
        detail = (result.stderr or result.stdout)[-1200:]
        raise RuntimeError(f"docker pull failed for {name} ({elapsed:.1f}s):\n{detail}")
    print(f"OK   {name} ({elapsed:.1f}s)")


def tag(source: str, target: str) -> None:
    print(f"TAG  {source} -> {target}")
    result = run(["docker", "tag", source, target], timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)


def check_daemon_mirrors() -> list[str]:
    result = run(["docker", "info", "--format", "{{json .RegistryConfig.Mirrors}}"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr or "docker info failed")
    mirrors = json.loads(result.stdout.strip() or "[]")
    print(f"INFO registry-mirrors={mirrors}")
    if not mirrors:
        raise RuntimeError("No registry-mirrors configured in Docker daemon")
    return mirrors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mirror",
        default=DEFAULT_MIRROR,
        help="Explicit mirror host used for prefix pulls (default: docker.1ms.run)",
    )
    parser.add_argument(
        "--skip-swebench",
        action="store_true",
        help="Only validate alpine via the mirror (fast path)",
    )
    parser.add_argument(
        "--require-local-swebench",
        action="store_true",
        help="Fail unless the official-named SWE-bench image already exists locally",
    )
    args = parser.parse_args()

    try:
        check_daemon_mirrors()

        alpine_mirror = f"{args.mirror}/{ALPINE_REF}"
        if not image_exists(alpine_mirror) and not image_exists("alpine:3.20"):
            pull(alpine_mirror, timeout=300)
        elif not image_exists(alpine_mirror):
            pull(alpine_mirror, timeout=300)
        print("PASS alpine mirror pull/tag path")

        if args.require_local_swebench:
            if not image_exists(SWEB_IMAGE):
                raise RuntimeError(
                    f"Required local image missing: {SWEB_IMAGE}. "
                    "Run without --require-local-swebench to pull it via the mirror."
                )
            print(f"PASS local SWE-bench image present: {SWEB_IMAGE}")
            return 0

        if args.skip_swebench:
            print("PASS mirror smoke (alpine only)")
            return 0

        mirror_sweb = f"{args.mirror}/{SWEB_IMAGE}"
        if not image_exists(SWEB_IMAGE):
            if not image_exists(mirror_sweb):
                pull(mirror_sweb, timeout=3600)
            tag(mirror_sweb, SWEB_IMAGE)
        else:
            print(f"SKIP pull; already have {SWEB_IMAGE}")

        if not image_exists(SWEB_IMAGE):
            raise RuntimeError(f"Retag failed; missing {SWEB_IMAGE}")

        size = run(
            [
                "docker",
                "image",
                "inspect",
                SWEB_IMAGE,
                "--format",
                "{{.Size}}",
            ]
        ).stdout.strip()
        print(f"PASS SWE-bench retag path size_bytes={size}")
        print("PASS docker mirror smoke")
        return 0
    except Exception as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
