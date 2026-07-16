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

## Operational quota accounting

- Keep shared usage and registry-backed additional quotas in separate audit
  lanes. Shared snapshots live in `usage_history`; a model mapped through
  `config/additional_quota_registry.json` uses its canonical
  `additional_usage_history` lane and must not be blended into shared fleet
  runway.
- Treat window names as storage identities, not assumptions about duration.
  Use the persisted window duration and reset timestamp to identify the active
  short, weekly, or monthly meter, especially when upstream changes which
  window it reports in the primary slot.
- Derive current fleet usage from the latest persisted row per account, quota
  lane, and window. Selection-log `remaining_credits` values are routing
  scores derived by the balancer, not provider accounting truth.
- Measure burn over multiple same-reset-cycle windows. Compare the observed
  points per hour with the sustainable rate
  `remaining quota points / hours until reset`, and report a range rather
  than presenting active-hour traffic as a flat forecast. Recompute after a
  traffic, cache, account-pool, or model-routing change.
