## 1. TTFT-split histograms

- [x] 1.1 Add `stream_first_event_seconds` and `stream_first_token_seconds` histograms (labels: transport, model; coarse buckets 0.5-120s) to `app/core/metrics/prometheus.py` with no-op fallback parity
- [x] 1.2 Record first-event observation after the first upstream SSE line and first-token observation where `latency_first_token_ms` is set in `app/modules/proxy/_service/streaming/mixin.py` (both text-delta sites)
- [x] 1.3 Unit test: observations recorded with correct labels on success; nothing recorded when the stream errors before the first event

## 2. Prompt-cache ratio canary

- [x] 2.1 Add settings knobs: `prompt_cache_canary_enabled`, `prompt_cache_canary_interval_seconds`, `prompt_cache_canary_window_seconds`, `prompt_cache_canary_min_input_tokens`, `prompt_cache_canary_ratio_threshold`
- [x] 2.2 Add `codex_lb_prompt_cache_ratio` gauge (label: model) to prometheus module
- [x] 2.3 Implement `PromptCacheCanaryScheduler` (leader-elected, stop-event loop per `StickySessionCleanupScheduler` pattern) querying per-model cached/input sums over the rolling window from request logs (`request_kind='normal'`, status success)
- [x] 2.4 Wire scheduler start/stop into app lifespan
- [x] 2.5 Unit tests: gauge update, WARNING on low ratio + volume, no warning below min volume, disabled setting skips runs

## 3. Dashboard cached-percentage fix

- [x] 3.1 Expose input-token total in dashboard metrics payload (`app/modules/usage/builders.py`, schema additions)
- [x] 3.2 Update frontend `DashboardMetricsSchema` with nullable `inputTokens`; pass it to `formatCachedTokensMeta`
- [x] 3.3 Update `formatCachedTokensMeta` to accept optional input-token denominator with fallback to combined total; update tests for both paths
- [x] 3.4 Frontend tests pass (`npm test` or repo equivalent) and backend usage tests pass

## 4. Validate and ship

- [x] 4.1 `openspec validate --specs` passes; focused pytest for touched modules passes
- [x] 4.2 Deploy via commit -> push -> `./update.sh`; verify new metrics appear on :9090/metrics and canary logs its first sample
