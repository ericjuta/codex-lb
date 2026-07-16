## Purpose and scope

Live quota ingestion keeps busy-account usage fresher than the background poller. This follow-up defines which upstream signal owns a successful HTTP/SSE turn after production history showed that response headers and terminal stream events can disagree.

The scope is limited to source precedence at the HTTP/SSE tap points. Parsing, persistence, dashboard rendering, polling, WebSocket event ingestion, and throttling remain unchanged.

## Decision and rationale

The terminal `codex.rate_limits` event owns successful HTTP/SSE quota state. Successful-response headers are provisional transport metadata and are not independently persisted. Error-response headers remain a live source because a rejected request may not produce a terminal rate-limit event, and the saturated-window snapshot is operationally important.

Retaining both successful sources was considered, including ordering or delaying header writes. That still leaves concurrent requests able to interleave different snapshot families and makes correctness depend on timing. A single successful-turn authority removes that race at the source.

## Constraints and failure modes

- Ingestion remains fire-and-forget and must not delay the proxied response.
- The account attribution contract is unchanged.
- The background poller remains the fallback for accounts without live event traffic.
- A successful stream that omits `codex.rate_limits` produces no header-derived live snapshot; polling repairs freshness.
- Error headers continue through the existing parser and may be ignored when they contain no usable window.

## Concrete example

A successful response begins with a primary header reporting 9% used and later emits a terminal `codex.rate_limits` event reporting 56% for the same weekly window. Persisting both lets the dashboard alternate between 9% and 56% as concurrent requests finish. With event precedence, only 56% enters usage history. A separate 429 response reporting 91% in its headers still enters usage history because no terminal event is expected.

## Operations

After deployment, weekly history should stop alternating between header-only rows and event rows for the same account. Existing conflicting rows remain historical data; the dashboard's latest snapshot stabilizes as new terminal events or background polls replace them.
