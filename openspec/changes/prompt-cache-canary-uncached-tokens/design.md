## Context

`PromptCacheCanaryScheduler` (app/modules/request_logs/prompt_cache_canary.py) samples per-model sums of `input_tokens` / `cached_input_tokens` from `request_logs` every `interval_seconds` on the leader replica, exports `codex_lb_prompt_cache_ratio`, and warns when ratio < blanket threshold with sufficient volume. Live evidence (2026-07-14): delta-transport rollout dropped sol avg input 123k -> 52k while avg uncached tokens fell 7.8k -> 6.4k — a cache win reported as ratio decline; spark's healthy baseline (~0.2) sits permanently under the 0.5 threshold, causing continuous false alarms.

## Goals / Non-Goals

**Goals:**
- Alert on the economically meaningful quantity: average uncached input tokens per request, per model.
- Allow per-model baselines so short-job lanes stop false-alarming without raising blanket sensitivity.
- Keep existing gauges/log lines stable for current dashboards.

**Non-Goals:**
- No alert delivery changes (still log-warning based).
- No schema/migration changes; `request_logs` already has the needed columns.
- No per-account or per-transport breakdown (future work if needed).
- No change to sampling cadence or leader election.

## Decisions

1. **Dual signal, not replacement.** Ratio gauge and warning stay; a new gauge `codex_lb_prompt_cache_uncached_tokens_per_request{model}` is exported every sample. Rationale: ratio is still useful for full-replay lanes and existing dashboards reference it.
2. **Uncached-token alerting is opt-in per model or via a blanket threshold default of 0 (disabled).** `prompt_cache_canary_uncached_tokens_threshold: int = 0` (0 = off) plus `prompt_cache_canary_model_uncached_tokens_thresholds: dict[str, int]`. A model with an uncached threshold set alerts when avg uncached tokens/request exceeds it; this avoids inventing universal baselines.
3. **Per-model ratio overrides.** `prompt_cache_canary_model_ratio_thresholds: dict[str, float]` overrides the blanket ratio threshold per model (e.g. spark: 0.15). Empty dict default preserves current behavior exactly.
4. **Single query extension.** Add `func.count()` to the existing grouped select rather than a second query; avg uncached = (sum_input - sum_cached) / count.
5. **Settings use pydantic dict fields** parsed from env as JSON (consistent with existing settings patterns in `app/core/config/settings.py`).

## Risks / Trade-offs

- Absolute uncached thresholds are workload-sensitive; a legitimate traffic-mix shift (longer prompts) can trip them. Mitigation: opt-in per model, threshold chosen from observed baseline.
- Dict-valued env settings are easy to mistype; mitigated by pydantic validation failing fast at startup.
- Prometheus cardinality grows by one gauge per model — same cardinality class as the existing ratio gauge.
