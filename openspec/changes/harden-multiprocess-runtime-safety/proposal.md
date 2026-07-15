## Why

The fork runs multiple worker processes against shared PostgreSQL, but three
runtime paths still rely on process-local or single-runner assumptions:
concurrent startup migrations can race, peer workers can erase a persisted
upstream rate-limit cooldown, and legitimate bridge gate contention fails after
one short admission timeout. These gaps can crash startup, prematurely reuse a
throttled account, or reject continuity-bound requests while usable capacity is
merely busy.

## What Changes

- Serialize Alembic upgrade and stamp operations across processes, re-checking
  migration state after lock acquisition and reporting schemas newer than the
  running build accurately.
- Persist inferred upstream 429 cooldown deadlines so all workers honor the
  same block, including a bounded floor for legacy rows without a reset
  timestamp.
- Treat HTTP bridge response-create gate contention as a recoverable,
  budget-bounded capacity wait while preserving soft-affinity reroute,
  queue-full fail-fast behavior, and stuck-session retirement.
- Add focused cross-process and externally visible regression coverage for all
  three invariants.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `database-migrations`: startup upgrades and stamping are serialized across
  processes, and newer/unknown schema revisions fail with accurate diagnostics.
- `account-routing`: upstream 429 cooldowns become durable shared routing
  state that peer workers cannot clear before the effective deadline.
- `proxy-admission-control`: bridge response-create gate contention becomes a
  recoverable capacity wait bounded by the original bridge request budget.

## Impact

- Runtime code: database migration orchestration, proxy load-balancer state,
  usage-refresh recovery, and HTTP bridge streaming/admission helpers.
- Configuration: one migration-lock timeout setting with a documented
  `CODEX_LB_DATABASE_MIGRATION_LOCK_TIMEOUT_SECONDS` environment variable.
- Persistence: no new application tables or Alembic revisions; existing
  account cooldown fields and database-native locking primitives are reused.
- Compatibility: SQLite and PostgreSQL remain supported; ordinary
  single-process startup and uncontended bridge requests retain their current
  behavior.
