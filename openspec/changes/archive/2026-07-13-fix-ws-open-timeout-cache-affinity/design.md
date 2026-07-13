# Design: fix-ws-open-timeout-cache-affinity

## Context

The websocket connect path (`_service/websocket/mixin.py`) runs a `for attempt in range(max_attempts)` loop (max 3). On any retryable `ProxyResponseError`, `_decide_websocket_failover_action` returns `failover_next`, which adds the account to `excluded_account_ids` and re-selects with `reallocate_sticky=True`. A `websocket_open_timeout` (raised in `proxy_websocket.py` when the open handshake exceeds `upstream_connect_timeout_seconds`) is classified `retryable_transient`, so a single network-side connect stall permanently breaks prompt-cache stickiness for that request even though the account is healthy. Live evidence: ~1,500 such timeouts/4h, evenly spread across all 4 accounts (network-side SYN/TLS stalls of 3-8s, not account failures).

The cleanup scheduler (`sticky_sessions/cleanup_scheduler.py`) purges only `prompt_cache` mappings (plus bridge sessions and websocket continuity states). `codex_session` rows accumulate forever: 75,860 rows, 33k older than 30 days.

## Goals / Non-Goals

**Goals:**
- Preserve prompt-cache/sticky account affinity across transient websocket open timeouts.
- Bound `codex_session` sticky-row growth with an age-based retention purge.

**Non-Goals:**
- Changing the failover ladder for non-timeout failures (403s, upstream close codes, auth errors).
- Changing `upstream_connect_timeout_seconds` default in code (the deployment env override to 15s is ops config).
- Purging `sticky_thread` mappings.
- New Prometheus metrics (existing failover-decision counter already carries action labels).

## Decisions

1. **Same-account retry scoped to `websocket_open_timeout` only.** The HTTP bridge path already treats `_is_retryable_websocket_open_timeout` as same-contract retryable. The websocket path gets the analogous behavior: if `exc.failure_phase == "websocket_open_timeout"` and `retryable_same_contract` and this account has not yet had its same-account retry and budget remains, decide `retry_same_account` instead of `failover_next`. A per-request, per-account counter caps same-account retries at 1 to keep worst-case latency bounded (open timeouts are already multi-second).
2. **Retry decision lives in `_decide_websocket_failover_action`.** It already receives `exc`, `attempt`, and `request_state`; it gains the timeout-specific branch and logs `action=retry_same_account` through the existing "Failover decision" log line, keeping the observability contract (request id, transport, account id, attempt, failure class, action).
3. **Retention purge reuses the existing leader-elected cleanup loop.** New repository method `purge_codex_session_before(cutoff)` mirrors `purge_prompt_cache_before`. The scheduler computes `cutoff = now - sticky_codex_session_retention_days` and skips the step when the setting is `0`. Guarded like the other steps so failure does not break the loop.
4. **Setting is days-granularity** (`sticky_codex_session_retention_days: int = 30`, `ge=0`) because codex_session affinity is only useful while a CLI session is alive; 30 days is generous and matches observed live distribution (1,762 rows touched in last 24h).

## Risks / Trade-offs

- Same-account retry adds up to one extra open-timeout duration (~15s worst case with the new env) before failover for genuinely dead accounts. Bounded to one retry; the deadline/budget check prevents exceeding the request budget.
- If the upstream stall is account-correlated (not network), the retry delays recovery by one attempt. Evidence shows even distribution across accounts, so this is acceptable.
- Purging `codex_session` rows older than 30 days could drop affinity for a resumed months-old CLI session; the consequence is a fresh load-balancer selection, not an error.
