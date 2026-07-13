# Proposal: improve-sticky-failover-affinity

## Why

Live incident analysis (2026-07-12, ~1,500 network-side websocket open timeouts / 4h) exposed two remaining sticky-affinity gaps and one observability gap:

1. **Transport failover deletes prompt-cache mappings.** When a websocket connect attempt fails over (`reallocate_sticky=True` on retry selection), `_select_with_stickiness` deletes the `prompt_cache` row before re-placing. For network-class failures the pinned account is healthy — the outage path preserves the mapping (returns to the warm account after recovery), but the failover path destroys it. One transient blip permanently evicts a warm mapping.
2. **codex_session fallback persists forever.** A durable `codex_session` mapping rebinds to the fallback account on the first reallocation and never re-homes, even if the original account recovers seconds later.
3. **No affinity metric.** Sticky hit/miss can only be inferred from log archaeology; the incident diagnosis required manual 4-hour log correlation.

## What Changes

- Selection failover (`reallocate_sticky=True`) for **TTL-based kinds** (`prompt_cache`): pick a fallback for the current request but **preserve** the existing mapping (do not delete, do not persist fallback) so subsequent requests return to the warm account; the TTL remains the natural expiry. Deletion still happens when the pinned account left the pool or is permanently down.
- **Durable kinds** (`codex_session`): on reallocation the fallback is still persisted (a session must stay pinned somewhere durable), unchanged behavior.
- New Prometheus counter `codex_lb_sticky_selection_total{kind, outcome}` with outcomes `hit` (pinned account selected), `fallback` (pinned unavailable, fallback chosen, mapping preserved), `rebind` (mapping rewritten to a different account), `new` (no prior mapping).

## Capabilities

### Modified Capabilities

- `sticky-session-operations`:
  - Modified requirement: sticky fallback/reallocation semantics — TTL-kind mappings survive request-scoped failover.
  - New requirement: sticky selection outcomes are observable via a metric.

## Impact

- `app/modules/proxy/load_balancer.py`: `_select_with_stickiness` reallocation branch keys deletion/persistence off kind TTL-ness; outcome counter recorded at each return path.
- `app/core/metrics/prometheus.py`: new `sticky_selection_total` counter (both prometheus-present and fallback-None branches, `__all__`).
- Tests: `tests/unit/test_select_with_stickiness.py` — reallocate for prompt_cache preserves mapping; codex_session still persists fallback; outcome metric branches.
- No API, schema, or migration changes.
