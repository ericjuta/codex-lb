# Tasks: fix-ws-open-timeout-cache-affinity

## 1. Same-account retry for websocket open timeouts

- [x] 1.1 Add a per-request same-account open-timeout retry counter to the websocket connect request state (or local loop state) in `app/modules/proxy/_service/websocket/mixin.py`.
- [x] 1.2 Extend `_decide_websocket_failover_action` to return `retry_same_account` when the failure is `websocket_open_timeout` + `retryable_same_contract`, the account's retry has not been consumed, and remaining budget covers another attempt; log the action through the existing "Failover decision" line.
- [x] 1.3 Handle `retry_same_account` in the connect attempt loop: re-attempt the same account without adding it to `excluded_account_ids` and without `reallocate_sticky`.
- [x] 1.4 Tests: open timeout then same-account retry succeeds (sticky preserved, action logged); second timeout on same account leads to failover_next; non-timeout failure gets no same-account retry; exhausted budget skips retry.

## 2. codex_session retention purge

- [x] 2.1 Add `sticky_codex_session_retention_days: int = Field(default=30, ge=0)` to `app/core/config/settings.py`.
- [x] 2.2 Add `purge_codex_session_before(cutoff)` to the sticky-sessions repository, mirroring `purge_prompt_cache_before`.
- [x] 2.3 Add a guarded purge step to `app/modules/sticky_sessions/cleanup_scheduler.py`: skip when retention is 0, log deleted count, failure must not break other steps.
- [x] 2.4 Tests: aged `codex_session` rows deleted, recent rows survive, `sticky_thread` untouched, retention=0 disables the purge.

## 3. Validation

- [x] 3.1 Run focused tests (websocket failover + cleanup scheduler) then the broader affected suites.
- [x] 3.2 `openspec validate --specs` (strict) passes.
