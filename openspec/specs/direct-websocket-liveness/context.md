# Direct WebSocket Liveness Context

## Purpose

Direct Responses WebSockets must either establish an upstream connection or
finish with a structured error within a predictable interval. A downstream
socket remaining open is not evidence that upstream connection setup is making
progress.

## Decisions

- The default per-account open-attempt timeout is 10 seconds.
- The default total connection-establishment budget is 20 seconds.
- The existing request deadline remains an outer ceiling when it expires first.
- A retryable open timeout excludes the failed account only for the current
  request and immediately tries another eligible account.
- Durable sticky mappings are not rewritten by transient transport failures.
- File and previous-response ownership remain hard account-pinning boundaries.

The settings are exposed as
`CODEX_LB_PROXY_WEBSOCKET_CONNECT_ATTEMPT_TIMEOUT_SECONDS` and
`CODEX_LB_PROXY_WEBSOCKET_CONNECT_BUDGET_SECONDS`. Both values must be
positive. Operators can tune them without changing failover semantics.

## Failure Modes

Local admission saturation remains a local overload response and is not
misclassified as an upstream account failure. An upstream open timeout records
the existing account error signal and lets existing health accounting drain a
repeatedly failing account without introducing a separate global breaker.

## Example

With the defaults, account A can consume at most 10 seconds opening a direct
WebSocket. A movable request may then use the remaining connection budget to
try account B. If no alternate succeeds before the 20-second total deadline,
the downstream receives the existing structured timeout error and the request
log settles terminally.
