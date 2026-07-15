## Context

The deployed fork uses shared PostgreSQL with multiple Uvicorn workers. Its
migration runner spans multiple short-lived connections, its balancer combines
durable account status with process-local health state, and its HTTP bridge
serializes turns through a per-session semaphore. The selected upstream fixes
address independent process-boundary failures in those three paths and must be
adapted without importing unrelated upstream release or migration history.

## Goals / Non-Goals

**Goals:**

- Make migration upgrade and stamp sequences mutually exclusive across
  processes while preserving SQLite and PostgreSQL support.
- Make 429 cooldown deadlines durable enough for peer workers and background
  refresh to honor.
- Let legitimate bridge gate contention wait and retry within the original
  request budget without weakening queue bounds or continuity rules.
- Preserve the fork's existing request normalization, bridge lifecycle,
  account-selection, and migration graph.

**Non-Goals:**

- Add tables or Alembic revisions.
- Introduce cluster-wide transient error counters or shared in-flight pressure.
- Change soft-affinity reroute precedence, bridge queue limits, or stable
  overload reason names.
- Port the separate compact reservation settlement change.

## Decisions

### Serialize the complete migration orchestration sequence

The lock wraps `run_upgrade()` and `stamp_revision()`, not Alembic's
`env.py`, because bootstrap, legacy remapping, version-table hardening, and
state inspection happen outside `command.upgrade`. PostgreSQL uses a
session-level advisory lock on a dedicated AUTOCOMMIT connection so the mutex
survives the runner's internal transactions. File-backed SQLite uses
`BEGIN IMMEDIATE` on a persistent adjacent sentinel database; in-memory
SQLite remains process-private and needs no lock.

After acquiring the lock, an upgrade-to-head re-inspects state and skips
Alembic execution when another process already reached head. Unknown revisions
are classified as schema-ahead and produce newer-build guidance rather than a
misleading behind-head message.

### Persist only authoritative cooldown state

When a 429 lacks explicit upstream reset metadata, the resolved deadline is
stored in the existing `accounts.reset_at` field. Parsed Retry-After hints are
rounded up to the next integer second; fallback backoff receives a 30-second
minimum. The existing `blocked_at` field provides a legacy-row floor.
Transient error counts, drain tiers, probe streaks, and in-flight pressure stay
process-local to avoid hot-path coordination writes.

Every recovery path checks the durable deadline before writing `ACTIVE`.
Early recovery remains limited to the worker whose runtime marker proves it
observed the current block.

### Retry bridge gate acquisition under one immutable deadline

Each semaphore acquisition remains bounded by the admission timeout. A timed
out acquisition can produce a capacity-wait plan, release the current queue
slot and account lease, emit progress, and retry. The request state carries the
original bridge deadline so retries and recovery paths cannot reset the budget.
Sleep and final acquisition attempts are clamped to remaining time, and
sleeping waiters reoccupy a queue slot so fan-out remains bounded.

Soft-affinity reroute runs first, queue-full stays fail-fast, and retired
sessions are never retried.

## Risks / Trade-offs

- **Session advisory locks require session-persistent PostgreSQL
  connections.** -> Migration connections must not use transaction-pooled
  PgBouncer endpoints.
- **A hung migration blocks peers until timeout.** -> The bounded timeout names
  the setting and lock in its failure.
- **A durable fallback cooldown may delay peer recovery briefly.** -> The
  30-second floor is bounded; the observing worker retains guarded early
  recovery.
- **Gate retries can retain requests longer than before.** -> The original
  bridge deadline, queue limit, per-attempt timeout, and retirement checks
  bound time and memory.

## Migration Plan

1. Deploy code with no schema migration.
2. Leave the 300-second migration-lock timeout unless startup migrations
   legitimately exceed it.
3. Monitor startup lock-wait logs, rate-limited account recovery, and bridge
   capacity-wait/timeout counters.
4. Roll back by reverting the code; sentinel SQLite lock files are harmless
   zero-row databases and may remain.

## Open Questions

None.
