# Proposal: fix-ws-open-timeout-cache-affinity

## Why

Live `codex-lb-direct` logs show ~1,500 `upstream_websocket_open_timeout` events per 4 hours, spread evenly across all accounts. Each timeout immediately excludes the sticky account and reallocates with `reallocate_sticky=True`, forfeiting prompt-cache affinity on ~31% of prompt-cache selections even though the account is healthy (the stalls are network-side TCP/TLS SYN-retransmit delays of 3-8s against the upstream edge, colliding with the 8s open timeout). Separately, `codex_session` sticky rows are never purged (75k+ rows, 33k older than 30 days), growing without bound.

## What Changes

- WebSocket connect failover: on a retryable `websocket_open_timeout` failure, retry the **same account once** (without excluding it or reallocating stickiness) before falling back to the existing exclude-and-reallocate failover ladder, budget permitting.
- Cleanup scheduler: purge `codex_session` sticky mappings whose `updated_at` is older than a configurable retention window (default 30 days; `0` disables). `sticky_thread` mappings remain untouched.
- Ops (already applied, config-only, no spec impact): raised `CODEX_LB_UPSTREAM_CONNECT_TIMEOUT_SECONDS` to 15 in the deployment env to absorb the observed 3-8s connect stalls.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `sticky-session-operations`:
  - New requirement: transient websocket open timeouts retry the same account before breaking prompt-cache stickiness.
  - Modified requirement: the cleanup loop's durable-mapping preservation is narrowed — `codex_session` mappings older than the retention window are purged; `sticky_thread` remains preserved regardless of age.

## Impact

- `app/modules/proxy/_service/websocket/mixin.py`: websocket connect attempt loop gains a bounded same-account retry for `websocket_open_timeout` before `failover_next`.
- `app/modules/proxy/service.py`: failover decision logging includes the same-account retry action.
- `app/modules/sticky_sessions/cleanup_scheduler.py` + sticky repository: new `codex_session` retention purge step.
- `app/core/config/settings.py`: new `sticky_codex_session_retention_days` setting (default 30, `0` disables).
- Tests: websocket failover retry behavior (timeout → same-account retry → success keeps sticky account; repeated timeout → failover), cleanup retention purge (old `codex_session` deleted, recent preserved, `sticky_thread` preserved).
- No API, schema, or migration changes.
