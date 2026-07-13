## Why

Live 24h data shows `gpt-5.6-luna` traffic achieves only ~1% upstream prompt-cache
hit rate while `gpt-5.3-codex-spark` and `gpt-5.6-sol` achieve 19-21% through the
same proxy. This is structural, not caused by the (now resolved) egress-IP
websocket throttle: luna sat at 0-2%/hour for the entire day, before and after
the sticky-affinity fixes and the NAT IP rotation. At ~479M input tokens / 6h,
every recovered 10 percentage points of cache hits is roughly 48M cached tokens
per 6h window of quota and latency savings.

## Observed Evidence (2026-07-13, live DB)

| Model | reqs (3h) | cache % | avg input |
|---|---|---|---|
| gpt-5.3-codex-spark | 1656 | 19.2% | ~27k |
| gpt-5.6-luna | 2292 | 1.3% | ~120k |
| gpt-5.6-terra | 94 | 1.1% | large |

Breakdown by request kind and effort (luna+spark, 3h):

| kind | effort | n | avg input | cache % |
|---|---|---|---|---|
| normal | high | 1451 | 27k | 22.7% |
| normal | max | 597 | 132k | 2.5% |
| prewarm | max | 575 | 112k | 0.3% |
| normal | xhigh | 470 | 123k | 0.7% |
| prewarm | high | 453 | 101k | 0.8% |

Root-cause hypotheses ranked by evidence:

1. **Concurrent multi-session interleaving per account.** Luna runs 4-7 parallel
   sessions across 4 accounts with ~120k-token contexts. Requests from different
   sessions interleave on the same account within seconds (verified in
   `request_logs`). OpenAI's prompt cache is capacity-bounded per
   (account, prompt_cache_key shard); large interleaved contexts evict each
   other before the next turn of the same session arrives. Spark's ~27k contexts
   survive; luna's ~120k contexts do not.
2. **Prewarm doubles pressure without hits.** ~50% of luna request volume is
   `request_kind=prewarm` (`generate=false` warmers, ~104k avg input, 0.5%
   cached). Each prewarm pushes another ~100k tokens through the same cache
   shard, roughly doubling eviction pressure for a warm-up that itself almost
   never lands a hit.
3. **Session-to-account fan-out.** 4 luna sessions used >1 account within 6h
   (failover-driven). Every account switch is a guaranteed cold start for that
   session's next turn. Now mostly mitigated by the sticky-exclusion fix, but
   rebalancing can still split a session's turns.
4. **WSS connect limit is NOT the lever.** `CODEX_LB_PROXY_UPSTREAM_WEBSOCKET_CONNECT_LIMIT`
   (currently 8) gates concurrent connection *handshakes*, not cache residency.
   Lowering it to 4 or 2 would only slow reconnect bursts and add latency; it
   cannot raise cache hits. No change recommended there beyond the existing 8.

## What Changes

Proposals in priority order (each independently shippable):

- **P1 — Per-account concurrent-session concentration.** Bias `_select_with_stickiness`
  new-key placement so concurrently-active large-context sticky families are
  spread across accounts instead of interleaving on one account (least-active-
  sticky-families placement instead of pure least-connections/round-robin for
  new `prompt_cache` keys). Goal: at most N (default 2) actively-streaming large
  sessions share one account's cache shard.
- **P2 — Prewarm suppression for cache-hostile traffic.** Skip or downgrade the
  HTTP-bridge prewarm when the payload is large (>= configurable threshold,
  default ~64k input bytes already partially exists via `first_turn_50k_gap_2m`)
  AND the account already has other active large sessions. Alternatively expose
  `..._prewarm_deny_api_key_ids` / canary percent as the rollout knob and measure
  via `http_bridge_prewarm_total` + per-kind cache rates.
- **P3 — Session-turn account pinning hardening (done, keep).** The
  2026-07-13 sticky-exclusion fix already prevents warm-mapping deletion during
  transient failover. Requirement is retained in spec form so regressions are
  testable.
- **P4 — Observability: per-model cache-hit-rate metric.** Add
  `codex_lb_prompt_cache_hit_ratio`-style counters labeled by model and
  request_kind (tokens_cached / tokens_input) so the dashboard can show the
  luna-vs-spark gap directly instead of requiring SQL.
- **Explicit non-change:** `CODEX_LB_PROXY_UPSTREAM_WEBSOCKET_CONNECT_LIMIT`
  stays at 8. Documented as rationale so the question "do we lower from 8 to
  4/2" has a recorded answer: no — it does not affect cache residency.

## Capabilities

### New Capabilities

- `prompt-cache-concentration`: rules for placing new prompt-cache sticky
  families across accounts to minimize per-account cache eviction pressure,
  and for suppressing prewarm traffic that raises eviction pressure without
  producing hits.

### Modified Capabilities

- `sticky-session-operations`: add requirement that new prompt-cache key
  placement considers per-account active-large-session count; add per-model
  cache observability requirement.

## Impact

- `app/modules/proxy/load_balancer.py` (`_select_with_stickiness` placement path)
- `app/modules/proxy/_service/http_bridge/request_submit.py` +
  `helpers.py` (prewarm eligibility)
- `app/core/metrics/prometheus.py` (new counters)
- `app/core/config/settings.py` (new knobs: max concurrent large sticky
  families per account, prewarm large-payload suppression threshold)
- No API/schema changes; no migration. Dashboard optional follow-up.
