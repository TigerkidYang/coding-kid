# Cloudflare Container smoke

This deployment verifies that the Cloudflare account can build, start, and
route requests to a minimal Container before adding Harbor or benchmark model
credentials.

It does not run Terminal-Bench and contains no API keys.

## Verified deployment

On 2026-08-06, Wrangler 4.119.0 deployed the Worker, SQLite-backed Durable
Object, and `basic` Container to the authenticated Cloudflare account. The
Container application reached `ready` state with one live instance, and an
external request returned HTTP 200 with:

```json
{"ok": true, "service": "coding-kid-terminal-bench-smoke", "location": "mia04", "region": "ENAM"}
```

Deployment URL:
`https://coding-kid-terminal-bench-smoke.runchangyang.workers.dev/health`

The local network maps `workers.dev` to a reserved interception address, so the
response was verified through an external read-only fetch path. No benchmark or
model request was made.

```powershell
npm install
npm run check
npm run deploy
```
