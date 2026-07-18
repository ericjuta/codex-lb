## Context

The direct Responses WebSocket path currently derives its connection deadline from the 600-second request budget and passes all remaining time to each upstream open. A retryable `websocket_open_timeout` is then retried once on the same account before normal failover. With the live 20-second global upstream connect timeout, two serial attempts can leave a client silent for about forty seconds even though another account is available.

The path already has the needed safety primitives: request-scoped account exclusion, sticky mappings that survive transport failover, strict owner pinning for files and `previous_response_id`, structured terminal errors, request-log settlement, per-account error recording, soft drain, and deterministic failover.

## Goals / Non-Goals

**Goals:**

- Bound the total time spent establishing a direct upstream WebSocket independently of the longer response request budget.
- Reserve time for an alternate account by bounding each upstream open attempt.
- Move retryable open-timeout recovery to another eligible account immediately.
- Preserve sticky and continuity ownership invariants and settle terminal failures visibly.
- Keep timeout values operator-configurable through typed settings.

**Non-Goals:**

- Changing HTTP bridge connection or replay behavior.
- Moving file-scoped or previous-response-scoped requests across accounts.
- Adding a second global circuit breaker or disabling the existing error-count, soft-drain, and deterministic-failover machinery.
- Guaranteeing transparent continuation after upstream has accepted a turn; this change only covers connection establishment before a socket is returned.

## Decisions

### Use a dedicated 20-second ladder and 10-second attempt cap

The direct connect deadline is the earlier of the existing request deadline and `started_at + proxy_websocket_connect_budget_seconds`. Refresh and selection remain inside that total deadline. Each upstream socket open receives the smaller of the remaining ladder budget and `proxy_websocket_connect_attempt_timeout_seconds`.

This separates session liveness from the global upstream connect timeout while retaining the outer request budget as a hard ceiling. Ten seconds leaves time for one alternate account under the default twenty-second ladder. Operators can tune both values without code changes; runtime clamping remains correct even if the attempt value exceeds the total value.

Alternative: lower `upstream_connect_timeout_seconds` globally. Rejected because that affects HTTP, bridge, compact, refresh, and other callers with different latency contracts.

### Fail over after the first retryable open timeout

The same-account retry action is removed for `websocket_open_timeout`. The failed account is recorded through the existing error handler, released, excluded for the current request, and the selector is invoked again when the request is movable and attempts/budget remain.

Alternative: retain a short same-account retry. Rejected because it consumes the alternate-account reserve on the same endpoint and was the observed freeze amplifier. Existing per-account error recording and soft drain provide cross-request adaptation; request-scoped exclusion provides immediate adaptation for the affected turn.

### Preserve owner pinning and durable affinity

File-owner and previous-response-owner requests continue to set `require_preferred_account`, so selection cannot cross accounts. Movable requests use the existing exclusion set without deleting or rebinding their stored sticky mapping. A later request can return to the original account after transient conditions clear.

### Reuse terminal error and settlement paths

When selection, refresh, or open work exhausts the ladder, the existing WebSocket timeout emitter sends the structured error and persists terminal request-log settlement. When no alternate exists after a retryable open timeout, the last classified upstream error is surfaced through the existing connect-failure path.

## Risks / Trade-offs

- [A healthy but slow upstream open may be abandoned after ten seconds] -> Both limits are operator-configurable and the defaults exceed ordinary handshake latency while prioritizing interactive recovery.
- [Immediate failover can reduce prompt-cache locality for one turn] -> Exclusion is request-scoped and the durable sticky mapping is preserved.
- [A pinned request cannot use an alternate and may fail sooner] -> Crossing owners would violate continuity; the client receives a structured retryable failure instead of an indefinite silent wait.
- [Selection or token refresh can consume part of the ladder] -> They intentionally share the same end-to-end establishment budget so all pre-open work is bounded.

## Migration Plan

1. Deploy the new defaults without environment overrides.
2. Verify the running build SHA, health endpoint, loaded setting values, and absence of startup errors.
3. Monitor `upstream_websocket_open_timeout`, failover-decision actions, terminal request errors, and direct WebSocket latency.
4. Roll back by deploying the previous build; no schema or persisted-data migration is involved.

## Open Questions

None.
