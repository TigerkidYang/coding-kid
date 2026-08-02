"""Run one authorized post-fix V04 CLI smoke without repeating the paired slice."""

from __future__ import annotations

import json
from pathlib import Path

import run_context_management_slice as suite

BASE = Path(__file__).resolve().parent
RETRY_MAX_REQUESTS = 60
REPORT = BASE / "cli_smoke_retry_report.json"


def main() -> int:
    suite.MAX_REQUESTS = RETRY_MAX_REQUESTS
    provider = suite.CountedProvider()
    result = suite.run_cli_smoke(provider)
    payload = {
        "model": suite.MODEL,
        "request_cap": RETRY_MAX_REQUESTS,
        "paid_requests": len(provider.requests),
        **result,
        "request_log": provider.requests,
    }
    REPORT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    passed = (
        result["process_pass"]
        and result["outcome_pass"]
        and result["error"] is None
        and len(provider.requests) <= RETRY_MAX_REQUESTS
    )
    print(
        f"CLI retry {'passed' if passed else 'failed'} with "
        f"{len(provider.requests)}/{RETRY_MAX_REQUESTS} paid requests"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
