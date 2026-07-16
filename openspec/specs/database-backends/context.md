## Overview

codex-lb is designed to be SQLite-first for simple local usage and container defaults. SQLite-specific resilience behavior (integrity checks, WAL tuning, recovery tooling) remains valuable for the default mode.

For higher concurrency or infrastructure-managed deployments, PostgreSQL support is enabled through SQLAlchemy async URLs using `asyncpg`.

## Decisions

- Keep SQLite as default to preserve zero-config startup.
- Accept PostgreSQL through `CODEX_LB_DATABASE_URL` only; no new configuration key aliases.
- Keep SQLite-specific recovery tooling SQLite-only; PostgreSQL operations should use PostgreSQL-native backup/recovery practices.
- Default SQLite startup validation to `quick` so normal boots stay fast while operators can still opt into `full` or `off`.
- Treat PostgreSQL as the greenfield baseline for new sustained deployments before increasing request-worker concurrency.

## Operational Notes

- SQLite default URL: `sqlite+aiosqlite:///~/.codex-lb/store.db`
- SQLite startup check mode: `CODEX_LB_DATABASE_SQLITE_STARTUP_CHECK_MODE=quick|full|off` (default `quick`)
- PostgreSQL example URL: `postgresql+asyncpg://codex_lb:codex_lb@127.0.0.1:5432/codex_lb`
- Pool controls (`database_pool_size`, `database_max_overflow`, `database_pool_timeout_seconds`) apply to non-memory SQLite and PostgreSQL engine creation.
- Background/request-adjacent DB pool controls (`database_background_pool_size`, `database_background_max_overflow`) default to the main pool settings, and can be lowered explicitly for deployments that want a smaller auxiliary pool.
- Local Compose and CI PostgreSQL coverage tracks PostgreSQL 18. For Dockerized PostgreSQL 18, mount persistent data at `/var/lib/postgresql`; the image's internal `PGDATA` lives below that path.
- Enable `pg_stat_statements` on sustained PostgreSQL deployments when query-level tuning is needed; it requires `shared_preload_libraries=pg_stat_statements`, a PostgreSQL restart, and `CREATE EXTENSION IF NOT EXISTS pg_stat_statements` in the application database.
- SQLite remains the local/smoke path. If SQLite lock retries or exhausted retry metrics rise during sustained serving, move the deployment to PostgreSQL rather than relying on unconstrained multi-worker SQLite.

### PostgreSQL temporary-spill diagnosis

- `pg_stat_database.temp_files` and `temp_bytes` are cumulative counters
  since the statistics reset; they are not current temporary-disk occupancy.
  Record the statistics reset or postmaster start time, sample the counters at
  two timestamps, and calculate the active byte and file rate before declaring
  an incident.
- Use `pg_stat_statements` temporary-block counters to attribute sustained
  spill to query families. Separate request-path queries from background
  cleanup, synchronization, and dashboard work before choosing a remedy.
- Correlate the delta with query latency, database waits, host I/O, request
  gate wait, and tail latency. A large cumulative counter without active
  growth or user-visible pressure is historical evidence, not a reason to
  restart PostgreSQL.
- `work_mem` applies per sort or hash operation and can multiply across
  concurrent statements. Prefer a query or index fix, or a scoped session
  override backed by `EXPLAIN (ANALYZE, BUFFERS)`, before raising it
  globally.

## Example

Use PostgreSQL while keeping all other defaults:

```bash
CODEX_LB_DATABASE_URL=postgresql+asyncpg://codex_lb:codex_lb@127.0.0.1:5432/codex_lb codex-lb
```

Use PostgreSQL for a sustained runtime profile with metrics enabled:

```bash
CODEX_LB_DATABASE_URL=postgresql+asyncpg://codex_lb:codex_lb@db.example.com:5432/codex_lb
CODEX_LB_UVICORN_WORKERS=2
CODEX_LB_METRICS_ENABLED=true
```

Use SQLite with explicit full startup validation:

```bash
CODEX_LB_DATABASE_SQLITE_STARTUP_CHECK_MODE=full codex-lb
```
