## 1. Migration serialization

- [x] 1.1 Add backend-specific cross-process migration locking with a bounded timeout setting.
- [x] 1.2 Wrap upgrade and stamp orchestration, re-check head after acquisition, and classify unknown revisions as schema-ahead.
- [x] 1.3 Add focused PostgreSQL/SQLite lock, wait-and-skip, timeout, and schema-ahead tests.

## 2. Durable rate-limit cooldowns

- [x] 2.1 Persist inferred 429 cooldown deadlines with integer rounding and the fallback minimum.
- [x] 2.2 Guard selection and usage-refresh recovery with the persisted deadline and current-block marker.
- [x] 2.3 Add cross-worker, legacy-row, Retry-After, and recovery regression tests.

## 3. Recoverable bridge gate contention

- [x] 3.1 Make gate-timeout contention wait-plan eligible while preserving reroute and queue-full precedence.
- [x] 3.2 Carry the original request deadline through retries, clamp waits, bound sleeping waiters, and skip retired sessions.
- [x] 3.3 Add unit and product-path coverage for recovery, budget exhaustion, queue bounds, and retired sessions.

## 4. Verification

- [x] 4.1 Run focused migration, balancer/usage, and bridge test suites.
- [x] 4.2 Run Ruff, ty, strict OpenSpec validation, migration policy, and single-head graph checks.
- [x] 4.3 Inspect the final diff and worktree status for intentional scope only.
