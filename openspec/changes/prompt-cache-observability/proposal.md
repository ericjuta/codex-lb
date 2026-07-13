## Why

The delta-mode websocket cache regression burned quota silently for weeks because
no surface showed per-model cache efficiency or alerted on its collapse, and the
next optimization decisions (transport A/B, prewarm re-eval, affinity tuning)
are blind without a TTFT breakdown separating codex-lb overhead from upstream
first-byte latency. Additionally the dashboard "Cached" stat divides cached input
tokens by total (input+output) tokens, understating the true cache hit ratio.

## What Changes

- Add TTFT-split Prometheus histograms on the streaming path: time from upstream
  stream start to first upstream SSE event, and to first text-delta event,
  labeled by transport and model, so operators can attribute latency to
  lb-overhead vs upstream service time vs generation start.
- Add a prompt-cache canary: a periodic background sampler that computes the
  rolling cache-hit ratio per model from request logs, exports it as a
  Prometheus gauge, and emits a WARNING log when a model with material volume
  falls below a configurable ratio threshold.
- Fix the dashboard cached-tokens stat to compute the percentage against input
  tokens (the denominator upstream caching actually applies to) instead of
  input+output tokens, keeping the cached count display unchanged.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `proxy-runtime-observability`: add TTFT-split histogram and cache-ratio
  canary requirements.
- `sticky-session-operations`: correct the dashboard cache-ratio display
  requirement (denominator = input tokens).

## Impact

- `app/core/metrics/prometheus.py`: two histograms + one gauge.
- `app/modules/proxy/_service/streaming/mixin.py`: record first-event /
  first-token timings.
- New periodic sampler (background task) for the cache-ratio canary +
  settings knobs (threshold, window, min volume).
- `app/modules/usage/builders.py` + `app/modules/usage/schemas.py`: expose
  input-token totals to the dashboard metrics payload.
- `frontend/src/utils/formatters.ts` (`formatCachedTokensMeta`),
  `frontend/src/features/dashboard/schemas.ts`, `utils.ts`: ratio fix.
- No API-breaking changes; additive schema field; no DB migration.
