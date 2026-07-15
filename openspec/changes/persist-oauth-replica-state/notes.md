# Implementation and validation notes

- Adapted the durable OAuth coordination mechanism from upstream `8e2ee2d3`.
- Did not port upstream `64b9f7bf` because targeted Team-seat reauthentication is unrelated to durable flow correctness and would change the fork's account-identity contract.
- Did not port upstream `b7bf87cf` because the fork already invalidates its account-selection and API-key caches after OAuth account persistence; broader routing-cache propagation is outside this change.
- Added one fork-parented revision, `20260715_130000_add_oauth_replica_state`, on the executable storage head `20260712_020000_add_api_key_usage_rollups` after rebasing onto fork main `4ffe742d`.
- Focused OAuth, repository race, and migration tests pass on SQLite. A fresh SQLite database also completed upgrade, downgrade to the fork parent, re-upgrade, drift check, migration-policy check, and single-head inspection.
- PostgreSQL and a live two-process deployment were not available in this isolated worktree. Cross-replica behavior is covered with separate process-local stores sharing the same test database; the repository emits PostgreSQL-native UPSERT for the production slot-claim path.
