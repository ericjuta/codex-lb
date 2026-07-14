## Why

The prompt-cache canary alerts on `cached_input_tokens / input_tokens` per model over a trailing window with a single blanket threshold (default 0.50). Two live failure modes make this metric misleading:

1. **Delta transports structurally deflate the ratio.** When Codex clients send incremental websocket deltas instead of full-history replays, per-request input shrinks (observed: sol 123k -> 52k avg input) while absolute uncached tokens stay flat or improve. The ratio drops even though cache economics improved, producing false alarms.
2. **Short-job workloads have a different healthy baseline.** Keyless/short-session lanes (observed: `gpt-5.3-codex-spark` deriver traffic at ~0.20-0.27 healthy baseline) sit permanently below the blanket 0.50 threshold, so the canary fires continuously and trains operators to ignore it.

The canary's purpose is regression detection; it should track the quantity operators pay for (uncached input tokens) and support per-model baselines.

## What Changes

- Add an **uncached-tokens-per-request** signal to the canary: per model, average `input_tokens - cached_input_tokens` per request over the window, exported as a Prometheus gauge and used for alerting alongside (not replacing) the ratio gauge.
- Add **per-model threshold overrides** for both the ratio threshold and the new uncached-tokens threshold, configured via settings (mapping of model name to threshold), falling back to the blanket defaults.
- Ratio alerting remains available but a model with a per-model override uses its own baseline; models with an uncached-tokens threshold alert on absolute uncached growth instead of ratio collapse.
- No change to sampling cadence, leader election, window semantics, or the `request_kind == "normal" AND status == "success"` row filter.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `proxy-runtime-observability`: prompt-cache canary requirements change from single ratio-threshold alerting to dual-signal (ratio + uncached-tokens-per-request) alerting with per-model threshold overrides.

## Impact

- `app/modules/request_logs/prompt_cache_canary.py`: query gains request count; new gauge export and threshold evaluation.
- `app/core/config/settings.py`: new settings `prompt_cache_canary_model_ratio_thresholds`, `prompt_cache_canary_uncached_tokens_threshold`, `prompt_cache_canary_model_uncached_tokens_thresholds`.
- `app/core/metrics/prometheus.py`: new gauge `codex_lb_prompt_cache_uncached_tokens_per_request`.
- Tests: unit coverage for threshold resolution and alert selection; regression coverage at the canary sampling path.
- Operators: existing ratio gauge and log line unchanged; new log line for uncached-token alerts.
