## 1. Replay proof

- [x] 1.1 Add a focused typed helper that projects response-owned bookkeeping and validates retained-output full resends.
- [x] 1.2 Validate exact self-contained direct tool call/output settlement against a durable manifest, including duplicate, collision, status, and unsupported-shape failures.
- [x] 1.3 Add focused unit tests for all safe and fail-closed replay-proof shapes.

## 2. Durable manifest persistence

- [x] 2.1 Add a forward Alembic migration and ORM field for the nullable response-bound tool-call manifest at the current migration head.
- [x] 2.2 Extend durable repository/coordinator contracts to encode, decode, atomically replace, and clear the manifest with the response alias.
- [x] 2.3 Add migration, repository round-trip, malformed-data, response-mismatch, and account-change clearing coverage.

## 3. Tool-call lifecycle reconciliation

- [x] 3.1 Track added and done tool-call lifecycle maps plus invalid-state evidence on each HTTP bridge request.
- [x] 3.2 Reconcile terminal output and persist a manifest only for complete, unique, supported lifecycles.
- [x] 3.3 Add lifecycle regression tests for incomplete, duplicate, mismatched, terminal-only, and unsupported parallel calls.

## 4. Fresh bridge preservation

- [x] 4.1 Classify verified durable full resends before anchor injection and preserve safe requests on the durable account with hard affinity.
- [x] 4.2 Prevent session-level re-injection for the first preserved request while leaving anchored and live-session paths unchanged.
- [x] 4.3 Add focused bridge and public `/v1/responses` regressions for retained output, exact tool loops, omitted calls, legacy rows, and unchanged anchored behavior.

## 5. Verification and handoff

- [x] 5.1 Run focused helper, repository, migration, unit bridge, and HTTP bridge integration tests.
- [x] 5.2 Run Ruff, formatting checks, changed-file type checks, architecture checks, and strict OpenSpec validation.
- [x] 5.3 Sync the verified delta into the main spec and archive the completed change.