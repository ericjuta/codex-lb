## Purpose and scope

Live quota ingestion keeps busy-account usage fresher than the background poller. This follow-up defines which upstream signal owns a successful HTTP/SSE turn after production history showed that response headers and terminal stream events can disagree.

Post-deployment verification exposed a second ownership boundary: the dashboard's primary weekly meter represents the shared Codex quota, while models listed in `config/additional_quota_registry.json` have independent meters stored in `additional_usage_history`. The scope now includes source precedence at HTTP/SSE tap points and quota-lane isolation at HTTP/SSE and WebSocket tap points. Parsing, persistence, dashboard rendering, polling, and throttling remain unchanged.

## Decision and rationale

The terminal `codex.rate_limits` event owns successful HTTP/SSE quota state. Successful-response headers are provisional transport metadata and are not independently persisted. Error-response headers remain a live source because a rejected request may not produce a terminal rate-limit event, and the saturated-window snapshot is operationally important.

Retaining both successful sources was considered, including ordering or delaying header writes. That still leaves concurrent requests able to interleave different snapshot families and makes correctness depend on timing. A single successful-turn authority removes that race at the source.

Rate-limit signals observed while serving an additional-quota model do not enter shared usage history. The proxy uses the existing model-to-additional-quota registry at every live tap point, while the additional-quota refresher continues to maintain the separate lane.

## Constraints and failure modes

- Ingestion remains fire-and-forget and must not delay the proxied response.
- The account attribution contract is unchanged.
- The background poller remains the fallback for accounts without live event traffic.
- A successful stream that omits `codex.rate_limits` produces no header-derived live snapshot; polling repairs freshness.
- Error headers continue through the existing parser and may be ignored when they contain no usable window.
- An unmapped or unknown model retains shared live-ingestion behavior; only registry-backed additional-quota models are excluded.

## Concrete examples

A successful response begins with a primary header reporting 9% used and later emits a terminal `codex.rate_limits` event reporting 56% for the same weekly window. Persisting both lets the dashboard alternate between 9% and 56% as concurrent requests finish. With event precedence, only 56% enters usage history. A separate 429 response reporting 91% in its headers still enters usage history because no terminal event is expected.

After that fix was deployed, a `gpt-5.3-codex-spark` request emitted a valid 25% Spark value while the same account's shared weekly value was 9%. Both values were correct for different lanes, but writing both into `usage_history` still made the dashboard alternate. Because Spark maps to `codex_spark`, its live event is now excluded from shared ingestion; an unmapped model such as `gpt-5.2` continues to publish shared usage normally.

## Operations

After deployment, weekly history should stop alternating between header-only rows, terminal shared-quota rows, and additional-quota rows for the same account. Existing conflicting rows remain historical data; the dashboard's latest snapshot stabilizes as new shared terminal events or background polls replace them. Additional-quota rows continue to refresh independently in `additional_usage_history`.
