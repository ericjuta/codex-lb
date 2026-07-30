## Why

Each application replica creates two independently pooled PostgreSQL engines, but Helm's documented capacity formula counts only one. At the production HPA ceiling this can admit roughly twice the documented connection budget and exhaust a default PostgreSQL server.

## What Changes

- Make the two-pool-per-replica topology explicit in the shared engine configuration.
- Pin the Helm-owned `app.cli` invocation to one worker so environment settings cannot silently multiply the chart's pool budget.
- Correct Helm capacity guidance and default/production values so the HPA ceiling leaves room for PostgreSQL-reserved slots, migrations, and operations.
- Add regression coverage that binds actual runtime engine roles, Helm values, and documented capacity math.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `database-backends`: Define the aggregate PostgreSQL connection budget across both per-replica engines.
- `deployment-installation`: Require Helm sizing guidance and production defaults to account for both engines.

## Impact

Affected surfaces are `app/db/session.py`, the Helm workload/defaults/production overlay, Helm documentation, OpenSpec database/deployment contracts, and focused unit/policy tests. No API, schema, migration, dependency, or production mutation is involved.
