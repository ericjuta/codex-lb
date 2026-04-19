# tune-runtime-throughput

## Why

Current `codex-lb` production serving on `eric-claw` runs as a single `uvicorn` process even though the host has multiple CPU cores and the runtime already ships with `uvloop` and `httptools`. That leaves safe throughput headroom unused for concurrent Codex CLI traffic. The deployment also leaves the dedicated Codex HTTP bridge prewarm flag off, which can add avoidable cold-start latency for bridge-backed Codex requests.

## What Changes

- add explicit runtime serving knobs for `uvicorn` workers, loop, and HTTP parser
- document those knobs in `.env.example`
- enable a higher-throughput runtime profile on the `eric-claw` deployment
- enable Codex HTTP bridge prewarm on the deployment to reduce cold-start bridge latency

## Impact

- improved concurrency headroom on multi-core hosts without changing default single-worker behavior for other environments
- lower first-turn latency for bridge-backed Codex requests when operators opt in
- no API contract change
