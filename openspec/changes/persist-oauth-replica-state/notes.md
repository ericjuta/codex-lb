# Implementation and validation notes

- Adapted the durable OAuth coordination mechanism from upstream `8e2ee2d3`.
- Audited the complete upstream squash against the fork implementation. The fork preserves all applicable correctness mechanisms: encrypted durable flows, uniform expiry normalization, atomic monotonic terminal writes, atomic device-slot ownership, same-replica start ordering, reconciliation at every flow-resolution entry point, and slot-gated token and terminal persistence.
- Did not port upstream `64b9f7bf` because targeted Team-seat reauthentication is unrelated to durable flow correctness and would change the fork's account-identity contract.
- Did not port upstream `b7bf87cf` because the fork already invalidates its account-selection and API-key caches after OAuth account persistence; broader routing-cache propagation is outside this change.
- Kept the fork's combined, fork-parented migration instead of replaying upstream's two-revision Alembic chain, preserving a single executable head on fork ancestry.
- Kept fork-native account persistence and cache invalidation. The upstream `intended_account_id` and targeted Team-seat reauthentication contract are not exposed by this fork.
- Extended the upstream behavior for this fork's dashboard contract: unscoped status and complete calls reconcile the process-local current flow id, and callback-server shutdown consults durable pending browser flows across replicas.
- Added one fork-parented revision, `20260715_130000_add_oauth_replica_state`, on the executable storage head `20260712_020000_add_api_key_usage_rollups` after rebasing onto fork main `4ffe742d`.
- Focused OAuth, repository race, and migration tests pass on SQLite. A fresh SQLite database also completed upgrade, downgrade to the fork parent, re-upgrade, drift check, migration-policy check, and single-head inspection.
- Cross-replica behavior is covered with separate process-local stores sharing the same test database. The final current-worktree PostgreSQL run passed all 50 OAuth and PostgreSQL migration-contract tests. A fresh PostgreSQL database also completed head upgrade, downgrade to `20260712_020000_add_api_key_usage_rollups`, re-upgrade to `20260715_130000_add_oauth_replica_state`, migration-policy validation, and a no-drift schema check.
