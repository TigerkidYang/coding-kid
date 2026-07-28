"""Safely prepare official SWE-bench images through a domestic mirror only."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

DEFAULT_MIRROR = "docker.1ms.run"
ALLOWED_MIRRORS = {DEFAULT_MIRROR}
DEFAULT_RETRIES = 3
MIRROR_DNS_URL = "https://dns.alidns.com/resolve?name=docker.1ms.run&type=A"
APPROVED_MIRROR_NETWORKS = (ipaddress.ip_network("101.227.21.0/24"),)


def instance_image(instance_id: str) -> str:
    encoded = instance_id.replace("__", "_1776_")
    return f"swebench/sweb.eval.x86_64.{encoded}:latest"


def run(
    command: list[str],
    *,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def load_ids(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        ids = data
    else:
        ids = data.get("instance_ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(x, str) for x in ids):
        raise ValueError(f"{path} must contain a non-empty instance_ids string list")
    return ids


def image_id(name: str) -> str | None:
    result = run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", name],
        timeout=60,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def verify_pair(mirror: str, official: str) -> str:
    mirrored = f"{mirror}/{official}"
    mirror_id = image_id(mirrored)
    official_id = image_id(official)
    if not mirror_id:
        raise RuntimeError(f"missing domestic image tag: {mirrored}")
    if not official_id:
        raise RuntimeError(f"missing official local image tag: {official}")
    if mirror_id != official_id:
        raise RuntimeError(
            f"image ID mismatch: domestic={mirror_id} official={official_id}"
        )
    return official_id


def pull_domestic(mirror: str, official: str, retries: int) -> None:
    if mirror not in ALLOWED_MIRRORS:
        raise ValueError(
            f"mirror {mirror!r} is not allowlisted; allowed={sorted(ALLOWED_MIRRORS)}"
        )
    mirrored = f"{mirror}/{official}"
    if image_id(mirrored):
        print(f"SKIP {mirrored} (already local)", flush=True)
    else:
        last_error = ""
        for attempt in range(1, retries + 1):
            print(f"PULL {mirrored} attempt={attempt}/{retries}", flush=True)
            started = time.perf_counter()
            result = run(["docker", "pull", mirrored], timeout=7200)
            elapsed = time.perf_counter() - started
            if result.returncode == 0:
                print(f"PULLED {mirrored} elapsed={elapsed:.1f}s", flush=True)
                break
            last_error = (result.stderr or result.stdout)[-2000:]
            print(f"RETRY {mirrored}: {last_error.splitlines()[-1:]}", flush=True)
            time.sleep(min(30 * attempt, 90))
        else:
            raise RuntimeError(f"domestic pull failed: {mirrored}: {last_error}")

    result = run(["docker", "tag", mirrored, official], timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    verified_id = verify_pair(mirror, official)
    print(f"READY {official} id={verified_id}", flush=True)


def verify_network_preconditions(mirror: str) -> None:
    if mirror not in ALLOWED_MIRRORS:
        raise ValueError(
            f"mirror {mirror!r} is not allowlisted; allowed={sorted(ALLOWED_MIRRORS)}"
        )
    info = run(
        ["docker", "info", "--format", "{{json .RegistryConfig.Mirrors}}"],
        timeout=60,
    )
    if info.returncode != 0:
        raise RuntimeError("Docker daemon is not ready")
    configured = json.loads(info.stdout.strip() or "[]")
    expected = f"https://{mirror}/"
    if expected not in configured:
        raise RuntimeError(f"required daemon mirror is absent: {expected}")

    if sys.platform == "win32":
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "$p=(Get-ItemProperty "
                "'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet "
                "Settings').ProxyOverride -split ';'; "
                f"if ($p -contains '{mirror}') {{ exit 0 }} else {{ exit 1 }}"
            ),
        ]
        bypass = run(command, timeout=30)
        if bypass.returncode != 0:
            raise RuntimeError(
                f"{mirror} is missing from the Windows proxy bypass list"
            )

        clash_config = (
            Path(os.environ["APPDATA"]) / "com.follow" / "clash" / "config.yaml"
        )
        if clash_config.exists():
            config = clash_config.read_text(encoding="utf-8")
            direct_group = re.search(
                r'- name: "🎯 绕过代理"\s+proxies:\s+- "DIRECT"',
                config,
            )
            if not direct_group or '"GEOIP,CN,🎯 绕过代理"' not in config:
                raise RuntimeError(
                    "FlClash is active without the required CN -> DIRECT rule"
                )

        request = urllib.request.Request(
            MIRROR_DNS_URL,
            headers={"User-Agent": "coding-kid-v02-evaluation"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            dns_result = json.load(response)
        public_ips = [
            ipaddress.ip_address(answer["data"])
            for answer in dns_result.get("Answer", [])
            if answer.get("type") == 1
        ]
        if not public_ips:
            raise RuntimeError(f"AliDNS returned no public A records for {mirror}")
        outside = [
            str(address)
            for address in public_ips
            if not any(address in network for network in APPROVED_MIRROR_NETWORKS)
        ]
        if outside:
            raise RuntimeError(
                f"{mirror} resolved outside approved domestic networks: {outside}"
            )
        print(
            f"PASS domestic DNS ips={','.join(str(address) for address in public_ips)}",
            flush=True,
        )
    print(f"PASS network preconditions mirror={mirror}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids-file", type=Path, required=True)
    parser.add_argument("--mirror", default=DEFAULT_MIRROR)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Do not pull; require both local tags with identical image IDs.",
    )
    args = parser.parse_args()

    try:
        ids = load_ids(args.ids_file)
        verify_network_preconditions(args.mirror)
        for instance_id in ids:
            official = instance_image(instance_id)
            if args.verify_only:
                verified_id = verify_pair(args.mirror, official)
                print(f"VERIFIED {official} id={verified_id}", flush=True)
            else:
                pull_domestic(args.mirror, official, args.retries)
        print(f"PASS all {len(ids)} required images are local", flush=True)
        return 0
    except Exception as error:
        print(f"FAIL {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
