# deployment-installation Specification

## Purpose

Define installation modes and smoke-test expectations so the Helm chart remains portable across supported deployments.
## Requirements
### Requirement: Helm chart is organized around install modes

The Helm chart MUST document and support three primary install modes: bundled PostgreSQL, direct external database, and external secrets. These install contracts MUST be portable across Kubernetes providers without requiring provider-specific chart forks.

#### Scenario: Bundled mode values exist

- **WHEN** a user wants a self-contained install
- **THEN** the chart provides a bundled mode values overlay with bundled PostgreSQL enabled

#### Scenario: External DB mode values exist

- **WHEN** a user wants to install against an already reachable PostgreSQL database
- **THEN** the chart provides an external DB values overlay and accepts direct DB URL or DB secret wiring

#### Scenario: External secrets mode values exist

- **WHEN** a user wants to source credentials from External Secrets Operator
- **THEN** the chart provides an external secrets values overlay that keeps migration and startup behavior fail-closed

### Requirement: Helm install modes are smoke-tested

The project MUST run automated Helm smoke installs for the easy-setup install modes in CI.

#### Scenario: Bundled and external DB modes are smoke tested

- **WHEN** CI runs Helm smoke installation checks
- **THEN** it installs the chart on a disposable Kubernetes cluster in bundled mode
- **AND** it installs the chart on a disposable Kubernetes cluster in external DB mode
- **AND** both installs reach a healthy testable state

### Requirement: Helm support policy is pinned to modern Kubernetes minors

The chart MUST declare a minimum supported Kubernetes version of `1.32`, and CI MUST validate chart rendering against a `1.35` baseline instead of older legacy minors.

#### Scenario: Chart metadata declares the minimum supported version

- **WHEN** a user inspects the chart metadata and README
- **THEN** the documented minimum supported Kubernetes version is `1.32`

#### Scenario: CI validates the modern baseline

- **WHEN** CI runs Kubernetes schema validation and kind-based smoke installs
- **THEN** the validation set includes Kubernetes `1.35`
- **AND** pre-`1.32` validation targets are not treated as the support baseline

### Requirement: Application data directory resolution is configurable and container-aware

The application MUST prioritize operator intent over container heuristics: a non-empty `CODEX_LB_DATA_DIR` MUST be the highest-priority data directory override. Without an override, an existing `$HOME/.codex-lb` MUST remain preferred, even inside a detected container. `/var/lib/codex-lb` MUST be used only when no override is configured, `$HOME/.codex-lb` does not exist, and container detection is true.

#### Scenario: Explicit data directory override wins

- **GIVEN** `CODEX_LB_DATA_DIR` is configured to a non-empty path
- **WHEN** application settings are loaded
- **THEN** the configured path is used as the data directory
- **AND** the container detection result does not override it

#### Scenario: Existing home data is reused inside an interactive container

- **GIVEN** `CODEX_LB_DATA_DIR` is not configured
- **AND** `$HOME/.codex-lb` already exists
- **AND** container detection is true
- **WHEN** application settings are loaded
- **THEN** `$HOME/.codex-lb` is used as the data directory
- **AND** `/var/lib/codex-lb` is not selected

#### Scenario: Container default is preserved when no home data exists

- **GIVEN** `CODEX_LB_DATA_DIR` is not configured
- **AND** `$HOME/.codex-lb` does not exist
- **AND** container detection is true
- **WHEN** application settings are loaded
- **THEN** `/var/lib/codex-lb` is used as the data directory

#### Scenario: Related default paths follow the resolved data directory

- **GIVEN** the resolved data directory differs from the module-import default
- **AND** the database URL, encryption key file, conversation archive directory, and response-create dump directory are not explicitly configured
- **WHEN** application settings and proxy dump helpers are used
- **THEN** the default SQLite database URL points at `<data-dir>/store.db`
- **AND** the default encryption key file points at `<data-dir>/encryption.key`
- **AND** the default conversation archive directory points at `<data-dir>/conversation-archive`
- **AND** oversized response-create dumps are written under `<data-dir>/debug/response-create-dumps`

#### Scenario: Explicit related path overrides are preserved

- **GIVEN** `CODEX_LB_DATA_DIR` is configured
- **AND** one or more related paths such as `CODEX_LB_DATABASE_URL`, `CODEX_LB_ENCRYPTION_KEY_FILE`, or `CODEX_LB_CONVERSATION_ARCHIVE_DIR` are explicitly configured
- **WHEN** application settings are loaded
- **THEN** each explicitly configured related path keeps its configured value
- **AND** only omitted related paths derive from the resolved data directory



### Requirement: Direct Docker respects addressable worker-pool startup

The direct Docker helper MUST rebuild the current checkout and recreate the local container without forcing one runtime worker. With multiple env-file workers and the HTTP responses session bridge enabled, image startup MUST use the addressable bridge worker pool, not plain multi-worker Uvicorn.

#### Scenario: direct Docker uses env-file worker count

- **WHEN** an operator runs the local Docker helper
- **AND** `.env.local` configures `CODEX_LB_UVICORN_WORKERS` greater than one
- **THEN** the helper does not add a conflicting `CODEX_LB_UVICORN_WORKERS=1` override
- **AND** the container startup path is responsible for selecting the safe worker-pool runtime

### Requirement: Docker guidance includes a SQLite-conservative profile

Docker installation guidance MUST include a SQLite-conservative runtime profile for operators who intentionally stay on SQLite. This profile MUST be distinct from the PostgreSQL higher-concurrency profile.

#### Scenario: SQLite-conservative Docker profile limits request workers

- **WHEN** an operator follows the documented SQLite-conservative Docker profile
- **THEN** the example keeps the SQLite database URL
- **AND** the example configures a single request worker or an equivalent write-serialized runtime
- **AND** the guidance explains that this profile trades throughput for fewer SQLite writer-lock failures

#### Scenario: Higher-concurrency Docker guidance remains PostgreSQL-backed

- **WHEN** an operator needs sustained multi-worker throughput
- **THEN** Docker guidance points to the PostgreSQL-backed profile rather than recommending unconstrained multi-worker SQLite
- **AND** the standard listener and OAuth callback ports remain unchanged

### Requirement: Docker installation documents a PostgreSQL performance profile

Docker-based installation guidance MUST provide a PostgreSQL-backed path for operators who need throughput beyond the default SQLite profile. This guidance MUST preserve the existing SQLite-first quick start for simple local usage.

#### Scenario: Docker quick start remains SQLite-first

- **WHEN** an operator follows the default Docker quick-start flow
- **THEN** the documented path continues to use the SQLite-backed default storage path
- **AND** PostgreSQL is not required for basic local startup

#### Scenario: Docker performance profile uses PostgreSQL

- **WHEN** an operator wants the documented higher-throughput Docker deployment profile
- **THEN** the guidance provides a PostgreSQL-backed example using `CODEX_LB_DATABASE_URL`
- **AND** the example keeps the standard `2455` and `1455` service ports
- **AND** the guidance identifies PostgreSQL as the recommended backend for that profile

### Requirement: Greenfield Docker runtime baseline is explicit and bridge-safe

Docker and operator installation guidance MUST define a PostgreSQL-backed greenfield runtime baseline for new sustained deployments. It MUST keep API port `2455` and OAuth callback port `1455` and use a bridge-safe worker strategy when the HTTP Responses session bridge is enabled.

#### Scenario: Greenfield baseline combines PostgreSQL and worker settings

- **WHEN** an operator follows the greenfield runtime baseline
- **THEN** the example configures `CODEX_LB_DATABASE_URL` for PostgreSQL
- **AND** it configures request-worker concurrency only through a bridge-safe startup path when the HTTP Responses session bridge remains enabled
- **AND** it keeps the standard listener and OAuth callback ports unchanged

#### Scenario: Plain multi-worker guidance requires bridge disabled

- **WHEN** the guidance shows plain Uvicorn multi-worker serving
- **THEN** it requires the HTTP Responses session bridge to be disabled
- **AND** it does not present plain multi-worker serving with a shared bridge instance id as a valid greenfield baseline

### Requirement: Greenfield baseline preserves operator tier preference

Greenfield baseline guidance for tiered traffic MUST preserve the operator's selected Codex CLI service tier. It MUST NOT recommend changing an existing ultrafast preference solely because the runtime is busy, and MUST instead require verification of requested versus actual upstream served tier.

#### Scenario: Greenfield baseline verifies ultrafast

- **WHEN** an operator uses Codex CLI with service_tier set to ultrafast
- **THEN** the greenfield baseline keeps that requested tier unchanged
- **AND** provides a verification path that compares requested_service_tier to actual_service_tier

### Requirement: Helm PostgreSQL helpers track the PostgreSQL runtime major

The Helm chart MUST use PostgreSQL client images on the same major runtime
baseline as bundled database coverage for migration and database initialization
helpers.

#### Scenario: Hook helper images use PostgreSQL 18

- **WHEN** the Helm chart renders the migration job with bundled PostgreSQL
  enabled
- **THEN** the wait-for-db init container uses a PostgreSQL 18 image
- **AND** the database initialization job uses a PostgreSQL 18 image

### Requirement: Docker runtime publishes the deployed Git identity

When an image is built with 'CODEX_LB_GIT_SHA', the image MUST expose that
value as the 'org.opencontainers.image.revision' label and as the
'CODEX_LB_BUILD_SHA' runtime environment value. HTTP responses with status
below 500 MUST include the same value in 'X-App-Build-SHA'. Builds without an
explicit SHA MUST use the literal value 'unknown'.

#### Scenario: Direct deployment exposes the checkout SHA

- **WHEN** the direct Docker helper builds the current checkout
- **THEN** it passes the checkout Git SHA to the image build
- **AND** the running health endpoint exposes that SHA in 'X-App-Build-SHA'

### Requirement: Bridge front proxy preserves worker response encoding

The addressable bridge worker pool front proxy MUST forward worker HTTP response bodies byte-for-byte without transparent decompression. With a `Content-Encoding` header, the downstream body MUST retain the matching encoded bytes.

#### Scenario: gzip-encoded dashboard asset passes through verbatim

- **WHEN** a worker responds to an asset request with `Content-Encoding: gzip` and a gzip-compressed body
- **THEN** the front proxy response preserves the `Content-Encoding: gzip` header
- **AND** the response body is the identical compressed bytes, decodable by the client

### Requirement: Response-create dump directory is bounded without configuration

Base installs MUST bound `<data-dir>/debug/response-create-dumps` without configuration. For oversized `response.create` payloads, the service MUST NOT write a dump whose fingerprint is already stored. After storing a dump, it MUST remove oldest dumps until at most a fixed number of pairs remain. Each pair's gzipped payload and meta file MUST be added and removed together. Duplicate suppression MUST be operator-visible in logs to preserve the dump path's recurrence signal.

#### Scenario: Repeated identical payloads are stored once

- **GIVEN** an oversized `response.create` payload has already been dumped
- **WHEN** a retry of the byte-identical payload is dumped again
- **THEN** no additional dump pair is written
- **AND** the originally stored dump pair is retained
- **AND** the suppressed duplicate is logged with its payload fingerprint and the path of the existing dump

#### Scenario: Distinct payloads are stored separately

- **GIVEN** an oversized `response.create` payload has already been dumped
- **WHEN** a different oversized payload is dumped
- **THEN** a separate dump pair is written for it

#### Scenario: Oldest dumps are pruned once the directory is full

- **GIVEN** the dump directory already holds the maximum number of dump pairs
- **WHEN** a dump for a new payload is written
- **THEN** the oldest dump pairs are removed so the maximum is not exceeded
- **AND** each removed payload file has its meta file removed with it
- **AND** the newly written dump pair is retained

#### Scenario: Dump retention needs no setting

- **GIVEN** a default installation with no dump-related configuration
- **WHEN** oversized response-create dumps are captured over time
- **THEN** duplicate suppression and pruning apply
- **AND** no `CODEX_LB_*` setting is required to bound the directory
