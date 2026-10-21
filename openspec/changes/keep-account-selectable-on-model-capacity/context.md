# Context

## Purpose

Stop a model-level condition from rotating and exhausting the whole account pool.

## Upstream provenance

Capacity carve-out of the unmerged `origin/feat/classify-account-exhaustion` (`excludes_account` /
`keeps_account_in_the_walk`). Skipped: the new `excludes_account` TypedDict field (the fork derives it from
`failure_class` + message to avoid changing every constructor), the burst/message-derived Retry-After stamping, and
the WebSocket/HTTP-bridge paths (not touched; they have their own replay bookkeeping).

## Decisions

- Health write and exclusion are separate decisions; the health write still lands.
- A usage-limit sentence outranks the capacity match.

## Failure modes

- Persistent capacity is bounded by the existing attempt/deadline budgets, not by pool exhaustion.

## Example

One account, capacity 400 then success: before, terminal 400; after, 200 on the second dispatch.
