## 1. Settings

- [x] 1.1 Add `prompt_cache_canary_model_ratio_thresholds: dict[str, float]` (default `{}`), `prompt_cache_canary_uncached_tokens_threshold: int` (default `0`, 0 = disabled), and `prompt_cache_canary_model_uncached_tokens_thresholds: dict[str, int]` (default `{}`) to `app/core/config/settings.py` with validation (ratio 0..1, tokens >= 0)

## 2. Metrics

- [x] 2.1 Add `codex_lb_prompt_cache_uncached_tokens_per_request{model}` gauge to `app/core/metrics/prometheus.py` alongside the existing ratio gauge

## 3. Canary scheduler

- [x] 3.1 Extend the grouped select in `PromptCacheCanaryScheduler._sample_once` with `func.count()`; compute avg uncached tokens per request per model
- [x] 3.2 Export the new gauge each sample; resolve per-model ratio threshold (override or blanket) for ratio warnings
- [x] 3.3 Add uncached-token alert path: warn when a model's configured (per-model or blanket, non-zero) uncached threshold is exceeded with the existing volume floor; log model, avg uncached tokens, threshold, window; no raw keys/prompts
- [x] 3.4 Thread new settings through `build_prompt_cache_canary_scheduler`

## 4. Tests

- [x] 4.1 Unit tests for threshold resolution (per-model override beats blanket; zero disables uncached alerting)
- [x] 4.2 Regression test at the canary sampling path: delta-shaped traffic (low ratio, low uncached) does not fire uncached alert; uncached regression fires despite healthy ratio; defaults preserve current ratio-warning behavior
- [x] 4.3 Run focused suite + `uv run ruff check`

## 5. Validation

- [x] 5.1 `openspec validate --specs` clean
- [x] 5.2 Deploy via ./update.sh and verify new gauge appears in /metrics with live values
