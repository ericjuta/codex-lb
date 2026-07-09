## Why

Concurrent quota planner ticks can select the same idempotency key. The repository currently recovers the race after PostgreSQL reports a unique-constraint error, which preserves the decision but creates recurring database error-log noise.

## What Changes

- Persist quota planner decisions with a database-native conflict-safe insert.
- Return the canonical existing decision when another writer has already claimed the same idempotency key.
- Preserve the original decision's audit fields and public API response while avoiding expected unique-constraint errors.
- Add regression coverage for the duplicate-key path.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `quota-phase-planner`: scheduler decision persistence must remain idempotent without producing an expected database uniqueness failure during a concurrent write.

## Impact

- Affects `app/modules/quota_planner/repository.py` and quota planner persistence tests.
- No API, schema, migration, or configuration changes.