# Live Usage Ingestion Context

## Purpose and scope

Direct Responses WebSocket traffic publishes the same passive usage evidence
as HTTP-bridge traffic. This keeps routing recovery and account-summary state
consistent regardless of which supported transport carried the response.

## Decision rationale

The direct WebSocket path reuses the existing passive usage-ingestion boundary
after decoding a valid upstream usage snapshot. Ingestion remains
fire-and-forget so telemetry persistence cannot delay or fail an otherwise
successful client response.

## Constraints and failure isolation

- Preserve the existing asynchronous ingestion boundary.
- Do not introduce new account-to-proxy module dependencies.
- Ignore malformed or absent usage snapshots.
- Isolate persistence failures from response forwarding and stream cleanup.
- Do not synthesize recovery evidence when the upstream payload lacks it.

## Failure mode and example

Without direct WebSocket ingestion, an account can successfully complete a
WebSocket response while its latest credits and reset windows remain invisible
to routing and `/api/accounts`. For example, positive credits recorded before a
block are not qualifying recovery evidence; the account must remain
`rate_limited` until a valid post-block snapshot arrives and is ingested.

## Operational notes

No migration or rollout flag is required. Validate both transport paths and
confirm ingestion failures do not interrupt response delivery. The normative
contract is in [spec.md](spec.md).
