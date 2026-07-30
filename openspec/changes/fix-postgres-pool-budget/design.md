## Context

A PostgreSQL replica creates one request-path engine at import time and a separate background engine during startup. The Helm profile leaves background-pool overrides unset, so both engines use the configured `database_pool_size` and `database_max_overflow`; its worst-case per-replica capacity is twice the configured per-engine capacity. Helm currently documents and sizes only one pool.

## Goals / Non-Goals

**Goals:**

- Derive the engine-count budget from the declared PostgreSQL engine roles used by the real creation paths.
- Keep the Helm-owned `app.cli` invocation on one worker per replica even when worker-related environment variables are present.
- Use the complete two-engine topology in Helm capacity guidance and policy tests.
- Keep default and production HPA ceilings at 80 application connections, leaving 20 raw server slots for PostgreSQL reservations, migrations, and operations.

**Non-Goals:**

- Changing which workloads use the background engine.
- Changing the existing independently configurable background-pool settings outside the Helm profile.
- Adding runtime discovery of PostgreSQL `max_connections`, a pooler, or a new setting.

## Decisions

- Keep both Helm-profile engines identically sized by leaving the optional background-pool overrides unset. Direct deployments retain their established ability to size the isolated background pool independently.
- Declare request-path and background-task PostgreSQL engine roles and require both creation paths to use a role-validating factory. Derive the per-worker engine count from those roles, so adding a declared role changes the budget automatically.
- Explicitly pass `--workers 1` in the Helm workload's `app.cli` command. This pins the topology covered by the chart capacity formula without changing the packaged entrypoint's explicit multi-worker mode for direct deployments.
- Size chart defaults at `(3 + 1) * 2 * 10 = 80`. Keep the production overlay at `(1 + 1) * 2 * 20 = 80`. A 20-slot raw reserve covers PostgreSQL's default three superuser-reserved slots, the migration path's two-connection peak (advisory-lock holder plus operation connection), and fifteen further operational connections.
- Test the budget from parsed Helm values against the role-derived runtime count, exercise both real engine creation paths, and verify that the Helm workload explicitly requests one worker.

## Risks / Trade-offs

- [Smaller pools can increase checkout waits during spikes] → Preserve three steady plus one overflow connection per default-chart engine, one steady plus one overflow per production engine, and retain the existing 30-second checkout timeout; operators with a larger server budget can tune upward using the documented formula.
- [A future pooled engine could invalidate Helm math] → Require every PostgreSQL application engine to declare a role through the shared factory and derive policy-test engine count from the role enum.
- [A customized workload can create multiple workers] → Keep multi-worker customizations outside the Helm capacity guarantee; operators that change the worker topology must account for every worker's two engine roles independently.
