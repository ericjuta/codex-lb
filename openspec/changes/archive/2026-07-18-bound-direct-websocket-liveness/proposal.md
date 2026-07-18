## Why

Direct WebSocket sessions can remain silent for roughly forty seconds when an upstream open handshake stalls because the proxy spends the full global connect timeout twice on the same account before trying another account. During an upstream edge incident this presents as frozen Codex sessions even while the service health endpoint remains green.

## What Changes

- Add a dedicated, operator-configurable total connect budget and per-account attempt timeout for direct WebSocket upstream opens.
- Fail over immediately to another eligible account after a retryable open-handshake timeout instead of serially retrying the same account.
- Preserve per-request exclusion, sticky-mapping, file-owner, and previous-response-owner invariants during failover.
- Emit the existing structured retryable terminal error and request-log settlement when the connect ladder cannot establish an upstream socket within budget.
- Add regression coverage for attempt clamping, total-budget clamping, movable failover, and pinned-account failure.

## Capabilities

### New Capabilities

- `direct-websocket-liveness`: Bounded direct WebSocket connection establishment, failover, terminal signaling, and operator controls.

### Modified Capabilities

- `sticky-session-operations`: Replace same-account open-timeout retry with immediate per-request exclusion while preserving the durable sticky mapping.

## Impact

- Configuration: `app/core/config/settings.py` gains two `CODEX_LB_` settings.
- Runtime: direct WebSocket connection selection and open-attempt budgeting in `app/modules/proxy/_service/websocket/mixin.py`.
- Tests: direct WebSocket proxy regression tests and configuration validation.
- Operations: deployment changes the timeout ladder for new direct WebSocket connection attempts; no schema or migration changes.
