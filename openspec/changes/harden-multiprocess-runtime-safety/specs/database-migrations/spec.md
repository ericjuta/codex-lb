## ADDED Requirements

### Requirement: Startup migrations are mutually exclusive across processes

The system SHALL serialize schema upgrades and stamps across all processes
sharing a database using a backend-appropriate cross-process mutex: a
PostgreSQL session-level advisory lock held on a dedicated connection for the
full migration sequence, or an exclusive write transaction on a sentinel
SQLite file adjacent to a file-backed SQLite database. In-memory SQLite MAY
skip the mutex because it is process-private.

After acquiring the mutex, an upgrade targeting `head` MUST re-inspect
migration state and MUST skip applying revisions when the schema is already at
head. Waiting for the mutex MUST be bounded by
`database_migration_lock_timeout_seconds`, defaulting to 300 seconds. A
timeout MUST identify the migration lock and the configuration setting.

#### Scenario: Two processes upgrade a fresh database concurrently

- **WHEN** two processes concurrently run upgrade to head against one fresh database
- **THEN** each pending revision is applied exactly once
- **AND** both processes report the head revision
- **AND** neither process fails with duplicate-object errors

#### Scenario: Waiting process observes completed migration

- **GIVEN** one process holds the migration lock while upgrading to head
- **WHEN** a waiting process acquires the lock after the first process completes
- **THEN** the waiting process succeeds without applying revisions again

#### Scenario: Migration lock wait times out

- **GIVEN** another process holds the migration lock beyond the configured timeout
- **WHEN** an upgrade or stamp attempts to acquire the lock
- **THEN** the operation fails with an error naming the migration lock and `database_migration_lock_timeout_seconds`

### Requirement: Schema newer than build is reported distinctly from schema behind head

Migration inspection SHALL classify revisions absent from the local Alembic
script directory and not covered by a legacy remap as unknown to the running
build. Startup and upgrade diagnostics MUST describe that state as a schema
newer than or unknown to the build and MUST NOT claim it is merely behind head.

#### Scenario: Startup migration disabled against a newer schema

- **GIVEN** startup migration is disabled
- **AND** the database revision is unknown to the running build
- **WHEN** the application starts
- **THEN** startup fails with guidance to deploy a matching or newer build or downgrade the schema
- **AND** the error does not claim the schema is behind head

#### Scenario: Startup migration enabled against a newer schema

- **GIVEN** startup migration is enabled
- **AND** the database revision is unknown to the running build
- **WHEN** the upgrade runs
- **THEN** it fails with the newer-build guidance before attempting a legacy remap
