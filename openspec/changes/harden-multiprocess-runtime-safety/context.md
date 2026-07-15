## Purpose and scope

This change ports three reviewed upstream correctness fixes into the divergent
fork. It is intentionally one integration lane because all three close
process-boundary failures exposed by running multiple workers against shared
state. It does not attempt to synchronize every in-memory runtime signal.

## Rationale

The implementation reuses existing durable fields and database primitives
instead of adding coordination tables. Migration locking must cover the full
runner rather than only Alembic's transaction. Account cooldown propagation
uses `reset_at` because readers already treat it as the authoritative recovery
deadline. Bridge contention retries preserve the existing session semaphore and
queue limits rather than adding a second scheduler.

## Constraints

- PostgreSQL migration locking requires a session-persistent connection.
- File-backed SQLite must use a separate sentinel file so Alembic DDL on the
  primary database cannot self-deadlock.
- Account-status recovery must retain compare-and-set persistence.
- Retry preparation must never replace the original bridge request deadline.
- Compact reservation settlement remains owned by its separate change.

## Failure modes

- A migration holder that stalls causes peers to fail after the configured
  timeout with an actionable error rather than race DDL.
- A legacy rate-limited row without `reset_at` remains blocked for at least
  30 seconds from `blocked_at`.
- A bridge queue at capacity still fails immediately with
  `bridge_queue_full`; only admitted gate contention enters the recoverable
  wait.
- A retired or closed bridge session is not retried after a timed-out
  acquisition.

## Example

Worker A receives an upstream 429 with no reset metadata and a fallback backoff
shorter than one second. It persists `RATE_LIMITED`, `blocked_at`, and a
`reset_at` at least 30 seconds in the future. Worker B loads the same row
while fresh usage still shows available quota; it keeps the account blocked
until the durable deadline instead of flipping it back to `ACTIVE`.

## Operational notes

The migration lock default is 300 seconds. Operators should investigate
repeated lock timeouts rather than disabling serialization. Bridge waits remain
bounded by the configured bridge request budget and continue emitting existing
capacity-wait diagnostics.
