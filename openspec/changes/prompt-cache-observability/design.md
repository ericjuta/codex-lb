## Context

The delta-mode websocket regression (see `improve-prompt-cache-hit-rate` notes)
showed two observability gaps: (1) no alertable per-model cache-hit signal, and
(2) TTFT (`latency_first_token_ms`) is recorded per request-log row but never
split between "upstream accepted the stream" and "first token generated", so we
cannot attribute the current ~14s HTTP TTFT between payload upload, upstream
queueing, and generation. The dashboard also computes the cached percentage as
`cached_input / (input + output)`, diluting the ratio operators actually care
about (`cached_input / input`).

Existing infrastructure to reuse:
- `app/core/metrics/prometheus.py` holds all counters/histograms with graceful
  no-op fallback when `prometheus_client` is absent; multiprocess mode already
  configured (`PROMETHEUS_MULTIPROC_DIR`).
- `app/modules/proxy/_service/streaming/mixin.py` already computes
  `latency_first_token_ms` at the text-delta event (lines ~777/946) and has
  `request_started_at` + first-event boundary (`iterator.__anext__()` at ~582).
- Periodic background tasks follow the `StickySessionCleanupScheduler` pattern
  (leader election, stop event, `get_background_session`).
- Dashboard metrics flow: `app/modules/usage/builders.py` →
  `DashboardMetricsSchema` (frontend `schemas.ts`) → `formatCachedTokensMeta`.

## Goals / Non-Goals

Goals:
- Attribute TTFT into upstream-first-event vs first-text-delta per transport+model.
- Alert (log WARNING + gauge) when a model's rolling cache ratio collapses.
- Dashboard cached percentage uses input tokens as denominator.

Non-Goals:
- No transport behavior changes (that is P2, blocked on the fork flag).
- No prewarm or affinity changes (P2/P3).
- No new alerting infrastructure (no Alertmanager wiring; log + gauge only).
- No per-session cache analytics UI.

## Decisions

1. **Histogram placement: streaming mixin, monotonic deltas from
   `request_started_at`.** Record two observations per stream:
   `first_event_seconds` right after the first upstream SSE line is received,
   and `first_token_seconds` where `latency_first_token_ms` is already set.
   Labels: `transport` (http|websocket), `model`. Alternative considered:
   instrumenting `core_stream_responses` in outbound clients — rejected because
   the mixin is transport-agnostic and already owns the timing state.
   Buckets: coarse latency buckets (0.5..120s) to bound cardinality.

2. **Canary as a lightweight scheduler querying `request_logs`.** A
   `PromptCacheCanaryScheduler` (same shape as `StickySessionCleanupScheduler`,
   leader-elected) runs every `interval_seconds` (default 300), aggregates
   `sum(cached_input_tokens)/sum(input_tokens)` per model over a rolling window
   (default 3600s) for `request_kind='normal'` successful rows, sets gauge
   `codex_lb_prompt_cache_ratio{model=...}`, and logs WARNING when
   `input >= min_input_tokens` (default 1M) and ratio < threshold (default 0.5).
   Alternative: compute from the existing Prometheus counters — rejected:
   counters lack windowing without a PromQL engine, and the DB query is cheap.

3. **Dashboard fix: additive `inputTokens` in metrics payload.** Extend the
   usage builders to also expose the input-token total alongside `tokens`;
   frontend passes `inputTokens` to `formatCachedTokensMeta` as the
   denominator. Keep the displayed cached count unchanged. When `inputTokens`
   is absent/null (older payloads), fall back to current behavior. Alternative:
   change the meaning of `tokens` — rejected as breaking.

4. **Settings knobs on the existing pydantic settings object** (env-overridable):
   `prompt_cache_canary_enabled` (default true),
   `prompt_cache_canary_interval_seconds` (300),
   `prompt_cache_canary_window_seconds` (3600),
   `prompt_cache_canary_min_input_tokens` (1_000_000),
   `prompt_cache_canary_ratio_threshold` (0.5).

## Risks / Trade-offs

- [Histogram cardinality: model label grows with catalog] → coarse buckets,
  two histograms only; models are bounded (~10).
- [Canary query load on request_logs] → indexed `requested_at` scan over 1h
  window every 5 min; negligible vs existing dashboards. Leader election
  prevents multi-worker duplication.
- [WARNING spam during legitimate low-cache workloads (fresh sessions)] →
  min-volume gate + 0.5 threshold well below healthy (0.9+) but above
  broken (0.02); threshold configurable.
- [Frontend fallback divergence] → keep old denominator only when inputTokens
  is null; test both paths.

## Migration Plan

Additive only: new metrics, new scheduler (enabled by default, off via env),
additive API field, frontend formatter change. Deploy via normal
commit → push → `./update.sh`. Rollback = revert commit; no schema/data
migration involved.

## Open Questions

- None blocking. Alertmanager/route integration deliberately deferred.
