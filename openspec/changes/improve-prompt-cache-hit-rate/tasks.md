## 1. Observability first (D3)

- [x] 1.1 Add `codex_lb_prompt_cache_input_tokens_total{model,request_kind}` and
      `codex_lb_prompt_cache_cached_tokens_total{model,request_kind}` counters to
      `app/core/metrics/prometheus.py` with a `_record_prompt_cache_usage` helper
- [x] 1.2 Record at the websocket usage-accounting point (`mixin.py` ~4211) and
      the HTTP-bridge equivalent; skip when usage is absent
- [x] 1.3 Unit tests: counters increment with usage, unchanged without usage

## 2. Concentration-aware placement (D1)

- [x] 2.1 Settings: `sticky_prompt_cache_max_active_large_families_per_account`
      (default 2), `sticky_prompt_cache_activity_window_seconds` (default 300),
      `sticky_prompt_cache_large_input_bytes` (default 65536)
- [x] 2.2 Helper to count recently-active large `prompt_cache` families per
      account (sticky repo query on `updated_at` + in-memory size class)
- [x] 2.3 Bias new-key placement in `_select_with_stickiness` (new-mapping path
      only); preserve eligibility order; fallback when all saturated
- [x] 2.4 Tests in `test_select_with_stickiness.py`: prefers unsaturated account,
      falls back when all saturated, never moves existing mappings

## 3. Prewarm suppression (D2)

- [x] 3.1 Add saturation gate to `_maybe_prewarm_http_bridge_session` with
      outcome `skipped_cache_pressure`
- [x] 3.2 Label support in `_record_http_bridge_prewarm_outcome`
- [x] 3.3 Tests: suppressed on saturated account, normal path on idle account

## 4. Validation

- [x] 4.1 `uv run ruff check` + focused pytest suites pass
- [x] 4.2 `openspec validate --specs` passes
- [ ] 4.3 Deploy via `./update.sh`; verify new counters at `:9090/metrics`
- [ ] 4.4 Multi-hour live check: luna `cached/input` ratio trend vs spark
      baseline; record findings in change notes
