## Context

Live 24h evidence (2026-07-13): `gpt-5.6-luna` traffic gets ~1% upstream
prompt-cache hits vs 19-21% for spark/sol. Structural causes identified from
`request_logs` + code reading, in evidence order:

1. 4-7 concurrent ~120k-token sessions interleave across only 4 accounts;
   OpenAI's per-account prompt cache evicts each session's prefix before its
   next turn arrives. Small-context spark traffic (~27k) survives the same
   interleaving.
2. ~50% of luna volume is `request_kind=prewarm` (~104k avg input, 0.5%
   cached) which doubles eviction pressure while almost never hitting.
3. Failover account switches guarantee cold starts (mostly fixed by the
   2026-07-13 sticky-exclusion change; 4 sessions still crossed accounts in 6h).

Explicit non-lever: `CODEX_LB_PROXY_UPSTREAM_WEBSOCKET_CONNECT_LIMIT` gates
connection handshakes only. Lowering 8 -> 4 or 2 cannot raise cache hits and
would add reconnect latency. Keep 8.

## Goals / Non-Goals

**Goals**
- Raise large-context (luna-class) cache hit rate by concentrating fewer
  concurrent large sessions per account cache shard.
- Stop prewarm from evicting warm contexts on already-busy accounts.
- Make per-model cache efficiency visible in Prometheus.

**Non-Goals**
- No change to websocket connect admission limits.
- No TTL tuning of `openai_cache_affinity_max_age_seconds` (needs days of
  metric baseline first).
- No migration; no API/schema changes.

## Decisions

### D1: Placement bias in `_select_with_stickiness` new-key path only

When no existing mapping is found for a `prompt_cache` key, rank otherwise-
eligible accounts by their count of recently-active large prompt-cache
families (from `sticky_sessions` updated_at within window, joined with an
in-memory input-size classification captured at selection time). Prefer
accounts under `sticky_prompt_cache_max_active_large_families_per_account`
(default 2). Tie-break with the existing selection order so health/budget
logic is preserved.

Alternative considered: hard per-account session cap — rejected because it can
starve selection when all accounts are busy; bias-with-fallback cannot.

Existing mappings are never moved: cache residency is worth more than perfect
balance, and the sticky-exclusion change already protects warm pins.

### D2: Prewarm suppression keyed on the same saturation signal

`_maybe_prewarm_http_bridge_session` gains one additional gate: if the resolved
account's recently-active large family count >= the concentration limit, skip
with outcome `skipped_cache_pressure` (new label on the existing
`http_bridge_prewarm_total` counter). This reuses the D1 counting helper.

Alternative considered: global prewarm kill switch for large payloads —
rejected; prewarm demonstrably helps small/idle-account cases and the existing
canary machinery already allows per-api-key rollback.

### D3: Token counters, not ratios, in Prometheus

Export two monotonic counters labeled `{model, request_kind}`; hit ratio is a
PromQL division. Avoids gauge/window semantics and matches the existing
`codex_lb_sticky_selection_total` counter style. Recorded at the same
usage-accounting point that writes `cached_input_tokens` to `request_logs`
(websocket mixin ~4211 and the HTTP-bridge equivalent).

### D4: Rollout & measurement

Ship D3 (observability) first, then D1, then D2. Judge success by
`cached_tokens_total / input_tokens_total` for `model=gpt-5.6-luna` moving from
~0.01 toward >=0.10 over a multi-hour window, with spark's ratio unchanged.

## Risks / Trade-offs

- **Placement bias vs load balance:** concentrating fewer large sessions per
  account can raise per-account burst load. Mitigated by keeping health/budget
  eligibility ahead of concentration preference (fallback scenario in spec).
- **Misclassification of "large":** input-bytes threshold is a proxy for token
  count. A wrong default only weakens the optimization; knob is configurable.
- **Prewarm suppression could cost TTFT on genuinely idle-cache accounts:**
  bounded by only suppressing at/above the saturation limit.

## Open Questions

- Should `sticky_prompt_cache_max_active_large_families_per_account` scale with
  plan type (pro vs free accounts may have different cache capacity)? Default
  static 2 until measured.
