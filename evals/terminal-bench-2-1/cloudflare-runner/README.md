# Cloudflare Terminal-Bench runner

This experimental runner places one Harbor trial inside each Cloudflare
`standard-4` Container. The outer Container starts rootless Docker with iptables
disabled, and Harbor applies a host-network Compose overlay as required by the
Cloudflare runtime.

The ignored build context contains the frozen Coding Kid wheel and the locally
inspected Terminal-Bench 2.1 task definitions. API credentials are Cloudflare
Worker secrets and must never be added to this directory.

`scheduler.py` keeps an atomic per-task state file, retries infrastructure
failures separately from benchmark outcomes, and resumes without repeating
completed trials. Generated state and logs live under ignored `runs/`.

`heartbeat_proxy.py` fronts a local OpenAI-compatible endpoint before it is
published through Cloudflare Tunnel. It uses padded chunked SSE heartbeats for
streaming Responses requests and chunked JSON-leading-whitespace heartbeats for
non-streaming Responses requests, allowing max-effort calls to exceed
Cloudflare's 120-second origin timeout without changing the returned JSON.

Required scheduler environment variables are intentionally supplied at launch
instead of stored here:

```text
CODING_KID_BENCH_API_KEY
CODING_KID_BENCH_RUN_ID
CODING_KID_BENCH_TRIAL_PREFIX
CODING_KID_BENCH_USE_BOOTSTRAP
CODING_KID_BENCH_FORCE_CONCURRENCY
CODING_KID_BENCH_MAX_CONCURRENCY
```
