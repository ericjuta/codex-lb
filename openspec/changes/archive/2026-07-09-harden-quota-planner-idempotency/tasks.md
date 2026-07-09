## 1. Atomic Persistence

- [x] 1.1 Replace the quota planner read-then-insert recovery path with a PostgreSQL/SQLite conflict-safe insert and canonical-row lookup.
- [x] 1.2 Preserve the existing repository signature and fail explicitly for unsupported database dialects.

## 2. Regression Coverage

- [x] 2.1 Update the duplicate-idempotency integration test to exercise the conflict-safe path and assert the original decision remains canonical.

## 3. Documentation and Verification

- [x] 3.1 Add durable rationale and operational monitoring guidance to the quota planner context document.
- [x] 3.2 Run the focused quota planner tests and OpenSpec validation.