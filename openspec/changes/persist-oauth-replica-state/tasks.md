## 1. Contract and baseline

- [x] 1.1 Validate the proposal, design, narrative context, and normative OAuth coordination spec before implementation.
- [x] 1.2 Capture the fork's current OAuth service entry points and current single Alembic head.

## 2. Persistence and migration

- [x] 2.1 Add typed OAuth flow and device-slot ORM models plus a request-scoped repository with encrypted verifier storage.
- [x] 2.2 Add one fork-parented Alembic revision that creates and cleanly removes both coordination tables.
- [x] 2.3 Add focused repository and migration coverage for expiry, monotonic status, atomic slot ownership, and the upgrade/downgrade path.

## 3. OAuth service coordination

- [x] 3.1 Persist browser and device flow creation and hydrate durable pending flows without changing fork account-identity behavior.
- [x] 3.2 Reconcile status, complete, manual callback, and browser callback against durable state before local decisions.
- [x] 3.3 Gate device account persistence and every terminal write on atomic slot ownership.
- [x] 3.4 Honor rejected callback error writes by reconciling to durable success.
- [x] 3.5 Reconcile unscoped status and complete requests through the local current flow id, and keep callback listeners active for durable pending browser flows.

## 4. Regression coverage

- [x] 4.1 Add cross-session browser callback, durable-terminal, expiry, and duplicate-callback regression tests.
- [x] 4.2 Add concurrent device-start, superseded-poller, and non-originating-complete regression tests.
- [x] 4.3 Add regression coverage for unscoped cross-replica terminal reconciliation and durable callback-listener liveness.
- [x] 4.4 Audit the compressed fork adaptation against upstream `8e2ee2d3` and add focused proof for timezone-aware expiry, cross-session monotonic writes, every reconciliation entry point, and same-replica device-start ordering.

## 5. Validation and review

- [x] 5.1 Run focused OAuth and migration tests plus the SQLite upgrade/downgrade/re-upgrade cycle and single-head check.
- [x] 5.2 Run Ruff, ty for changed production files, and strict OpenSpec validation.
- [x] 5.3 Inspect the final diff, commit history, and clean worktree status; record unavailable PostgreSQL or live-replica verification.
