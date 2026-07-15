## Context

Rate-limit handling keeps a precise `runtime.blocked_at` in the worker that observed the upstream 429, while the shared account row stores `blocked_at` as whole seconds. The existing local early-recovery gate correctly requires a current runtime marker, but it compares usage freshness with the less precise persisted value. Under enough scheduling delay for the short local backoff to expire, a usage row recorded immediately before the 429 in the same second can be mistaken for post-block evidence.

## Goals / Non-Goals

**Goals:**

- Preserve exact event ordering when the marking worker evaluates fresh-usage early recovery.
- Keep peer-worker persisted cooldown enforcement unchanged.
- Reproduce the subsecond ordering edge deterministically without timing sleeps.
- Keep live usage ingestion transport-complete for direct Responses WebSockets.
- Keep account-summary recovery aligned with the router's post-block evidence gate.

**Non-Goals:**

- Change sticky-session reallocation policy or its integration-test expectation.
- Change cooldown duration, database timestamp precision, schemas, or migrations.
- Change recovery for rows without a current local runtime block marker.

## Decisions

### Compare local freshness with the precise runtime marker

Within the existing early-recovery branch, compare the candidate usage timestamp with `runtime.blocked_at`. That branch already proves the runtime marker is present and at least as recent as the persisted marker, so the precise value is the authoritative chronology boundary for the worker that observed the 429.

Using the persisted value was rejected because integer truncation loses event order. Increasing the cooldown was rejected because it only changes how often the race appears. Persisting fractional timestamps was rejected because it expands this focused correction into a schema and compatibility change.

### Cover the edge at the state-derivation boundary

Add a unit case with a persisted block at `T`, a precise runtime block at `T + 0.8`, and a usage sample at `T + 0.7`. The local cooldown is expired to enter early recovery. The account must remain rate-limited because the usage sample predates the exact event even though it is newer than the persisted whole second.

The existing sticky-session integration expectation remains the product-path regression guard; no sleeps or weaker attempt assertions are introduced.

### Reuse the live hub at the direct WebSocket relay boundary

Inspect upstream text frames before downstream processing and publish only frames containing the existing event marker. Parsing and publication use the same fire-and-forget helpers as HTTP/SSE and the HTTP bridge, attributed to the serving account.

### Gate displayed recovery with routing-equivalent chronology

When a persisted `RATE_LIMITED` account maps to an active summary, require the relevant primary or long-window recovery row to be strictly newer than `blocked_at`. Use the same window-selection rules as routing, including the expired-primary/newer-available-long-window case. This prevents stale credits or stale capacity rows from making `/api/accounts` disagree with selection.

## Risks / Trade-offs

- **Risk: valid early recovery waits for truly post-block evidence** -> This is intentional; only samples strictly newer than the exact local event qualify.
- **Risk: peer behavior diverges from the marking worker** -> Peers continue using the persisted deadline by design because they do not possess the exact runtime event marker.
- **Trade-off: no persisted subsecond precision** -> The fix remains process-local and avoids migration risk while preserving the existing cross-process contract.
- **Trade-off: mapper duplicates a small routing evidence selector** -> Keeping it module-local avoids coupling account APIs to proxy internals; parity is locked by product-path tests and the shared normative requirement.
