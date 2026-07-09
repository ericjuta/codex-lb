## Context

The quota planner records scheduler decisions under a unique `idempotency_key`. The current read-then-insert sequence handles a duplicate-key race after the database rejects the insert, so the canonical audit row survives but PostgreSQL emits an avoidable error. The production log sweep found this path recurring for shadow no-op decisions.

## Goals / Non-Goals

**Goals:**
- Make decision creation atomic for PostgreSQL and SQLite.
- Return the single canonical decision for a colliding idempotency key without changing its original audit values.
- Preserve the existing repository method signature, schema, and dashboard response behavior.
- Cover the duplicate-key path with the existing integration test fixture.

**Non-Goals:**
- Changing planner scheduling, leader election, idempotency-key format, or audit retention.
- Adding a migration or changing the unique constraint.
- Generalizing a persistence abstraction beyond quota planner decisions.

## Decisions

- Use the repository's bound-dialect name to choose SQLAlchemy's PostgreSQL or SQLite `insert` constructor, matching established repository patterns. Unsupported dialects fail explicitly rather than silently falling back to a race-prone implementation.
- Issue `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING` for every decision write. This removes the read-before-write race and lets the database arbitrate competing writers without raising an expected uniqueness error.
- Commit the conflict-safe insert inside `sqlite_writer_section`, then query by idempotency key and return that persisted row. The post-commit read provides the inserted row or the winner's canonical row without relying on dialect-specific `RETURNING` behavior.
- Retain the existing unique constraint as the sole correctness boundary; no data migration is necessary.

## Risks / Trade-offs

- [One extra read after every decision write] → Decision writes are low-frequency scheduler/audit operations, and the read is required to return the canonical ORM model consistently across both supported dialects.
- [Unsupported future dialect] → Raise a clear runtime error at the repository boundary instead of silently restoring error-prone behavior.
- [Concurrent writer has not committed] → Database conflict handling waits for the contender's outcome; the post-commit lookup then returns the durable winner.

## Migration Plan

1. Deploy the application change; no database migration is required.
2. Monitor PostgreSQL logs for the previous `quota_planner_decisions_idempotency_key_key` signature.
3. Roll back the application image if necessary. Existing data and API behavior remain compatible.

## Open Questions

_None._