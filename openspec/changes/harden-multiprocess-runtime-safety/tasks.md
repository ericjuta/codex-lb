## 1. Migration serialization

- [ ] 1.1 Add backend-specific cross-process migration locking with a bounded timeout setting.
- [ ] 1.2 Wrap upgrade and stamp orchestration, re-check head after acquisition, and classify unknown revisions as schema-ahead.
- [ ] 1.3 Add focused PostgreSQL/SQLite lock, wait-and-skip, timeout, and schema-ahead tests.

## 2. Durable rate-limit cooldowns

- [ ] 2.1 Persist inferred 429 cooldown deadlines with integer rounding and the fallback minimum.
- [ ] 2.2 Guard selection and usage-refresh recovery with the persisted deadline and current-block marker.
- [ ] 2.3 Add cross-worker, legacy-row, Retry-After, and recovery regression tests.

## 3. Recoverable bridge gate contention

- [ ] 3.1 Make gate-timeout contention wait-plan eligible while preserving reroute and queue-full precedence.
- [ ] 3.2 Carry the original request deadline through retries, clamp waits, bound sleeping waiters, and skip retired sessions.
- [ ] 3.3 Add unit and product-path coverage for recovery, budget exhaustion, queue bounds, and retired sessions.

## 4. Verification

- [ ] 4.1 Run focused migration, balancer/usage, and bridge test suites.
- [ ] 4.2 Run Ruff, ty, strict OpenSpec validation, migration policy, and single-head graph checks.
- [ ] 4.3 Inspect the final diff and worktree status for intentional scope only.
