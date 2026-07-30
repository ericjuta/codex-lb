## ADDED Requirements

### Requirement: PostgreSQL connection budgets include every pooled engine

The application SHALL declare every independently pooled PostgreSQL engine role. The request-path and background-task engine creation paths MUST each use the shared role-aware PostgreSQL engine factory, and the engine-count budget MUST be derived from those declared roles. The Helm-owned `app.cli` invocation MUST explicitly request one worker per replica so the chart budget cannot be multiplied by worker-related environment settings.

#### Scenario: One replica reaches configured pool capacity

- **WHEN** both declared PostgreSQL engine roles in one Helm-profile worker reach `database_pool_size + database_max_overflow`
- **THEN** the replica's aggregate application connection capacity is `2 * (database_pool_size + database_max_overflow)`
- **AND** both engines were created through the role-aware factory counted by that formula

#### Scenario: Helm workload pins the budgeted worker count

- **GIVEN** worker-related environment settings request more than one worker
- **WHEN** the application starts through the Helm-owned `app.cli` command
- **THEN** the command explicitly requests one Uvicorn worker
- **AND** the replica creates only the request-path and background-task pools counted by the chart formula
- **AND** operators who customize the worker topology MUST expand the connection budget for every additional worker

#### Scenario: Test database disables pooling

- **WHEN** `CODEX_LB_TEST_DATABASE_URL` selects `NullPool`
- **THEN** pool sizing controls and the production pooled-engine budget do not apply to that test engine
