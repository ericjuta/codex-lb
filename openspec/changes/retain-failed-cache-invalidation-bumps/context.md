## Purpose

Make cross-replica cache invalidation survive a transient database failure at publish time.

## Upstream provenance

Soju06/codex-lb `fbb97519a` (#2545, "retain failed immediate invalidations"). Upstream builds on a retry/`_pending_bumps`/`request_bump` machinery the fork does not have, so the patch does not apply. This change ports only the narrow behavior: pending namespace set on the poller, flushed from the existing run loop.

## Decisions

- Reuse the 0.5 s poll tick as the retry cadence; no per-call retry loop, backoff, or extra tasks.
- A pending set keyed by the two fixed namespaces bounds memory.
- The pending marker is consumed before the write and re-added on any non-success (including `CancelledError`, via `finally`), so a concurrent re-request survives and an ambiguous interrupted commit is retried; a redundant version bump only re-runs idempotent peer callbacks.
- Upstream's `request_bump`/coalescing/direct-write retry attempts with SQLite lock backoff are not ported.

## Failure Modes

- Database unavailable for N ticks: the namespace is retried every tick (debug-logged after the first warning) until a write succeeds.
- Replica stops before a retry succeeds: pending state is lost; peers fall back to the cache TTL.

## Example

`DELETE /api/api-keys/{id}` commits, `bump(api_key)` fails on a connection error, the namespace becomes pending, the next tick writes version N+1, and peers clear their API-key cache on their next poll.
