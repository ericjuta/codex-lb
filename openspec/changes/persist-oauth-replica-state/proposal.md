## Why

Dashboard OAuth flow state is currently process-local, so callbacks, manual completion, and status polling can fail or observe stale state when requests land on a different replica or after the originating process restarts. The fork now explicitly supports hardened multi-process and PostgreSQL-backed deployments, making durable OAuth coordination a correctness requirement.

## What Changes

- Persist browser and device OAuth flow state in the database, encrypting PKCE verifiers with the existing token-encryption key.
- Reconcile every externally reachable OAuth entry point against durable state before acting on local runtime handles.
- Enforce monotonic terminal status updates so a successful flow cannot regress to an error during callback or poller races.
- Coordinate device flows with one atomic database slot so only the current originating poller may persist an account or terminal status.
- Expire abandoned flows uniformly and add migration and concurrency regression coverage.

## Capabilities

### New Capabilities

- `oauth-flow-coordination`: Durable, encrypted, multi-replica coordination and terminal-state rules for dashboard OAuth flows.

### Modified Capabilities

None.

## Impact

- Adds two database tables and a fork-parented Alembic migration.
- Adds an OAuth repository and updates OAuth service orchestration and dependency injection.
- Extends focused OAuth and migration integration coverage for SQLite and cross-session races.
- Does not change dashboard routes, response schemas, OAuth provider configuration, or account identity policy.
