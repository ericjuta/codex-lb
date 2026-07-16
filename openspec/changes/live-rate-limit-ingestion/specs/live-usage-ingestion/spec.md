## ADDED Requirements

### Requirement: Proxied responses feed passive usage snapshots

The proxy SHALL parse upstream rate-limit signals from proxied traffic — `x-codex-{primary,secondary}-used-percent`, `-window-minutes`, `-reset-at`, and `x-codex-credits-*` error-response headers, and `codex.rate_limits` stream events — into per-account usage snapshots attributed to the account that served the request. For successful HTTP/SSE responses, the terminal `codex.rate_limits` stream event SHALL be the persisted live usage source and response headers MUST NOT be independently persisted. Error-response headers SHALL be ingested because no terminal event may follow. Snapshots SHALL be persisted through the same usage-history storage contract the background poller uses (per-window rows with used percent, reset timestamp, window duration, and credits fields). The observation timestamp SHALL be captured before enqueueing, retained across queue and storage delays, and shared by every window row derived from one snapshot.

#### Scenario: Stream event updates usage rows

- **WHEN** a proxied response stream carries a `codex.rate_limits` event for an account
- **THEN** the account's primary and secondary usage rows reflect the event's used percentages, reset timestamps, and window durations without waiting for the next poll

#### Scenario: Successful response headers do not compete with the terminal event

- **WHEN** a successful upstream stream carries `x-codex-*` rate-limit headers and a terminal `codex.rate_limits` event with different values
- **THEN** only the terminal event snapshot is ingested for the serving account

#### Scenario: Error response headers update usage rows

- **WHEN** an upstream error response carries `x-codex-*` rate-limit headers
- **THEN** an equivalent snapshot is ingested for the serving account without waiting for a stream event

#### Scenario: Sibling rows share one observation time

- **WHEN** one live snapshot contains multiple usage windows
- **THEN** every persisted window row from that snapshot has the same `recorded_at` value

#### Scenario: Queue delay preserves observation time

- **WHEN** a live snapshot waits in the ingest queue before persistence
- **THEN** its `recorded_at` value reflects when the snapshot was enqueued rather than when the delayed write began

#### Scenario: Snapshots without any window are ignored

- **WHEN** a response carries no rate-limit headers and no rate-limit stream event
- **THEN** nothing is ingested

### Requirement: Live ingestion never impairs the serving path

Live usage ingestion MUST be fire-and-forget: parsing failures, storage failures, and backpressure MUST NOT fail, block, or slow the proxied request beyond enqueueing a snapshot. When the ingest queue is full, the oldest snapshot SHALL be dropped and the drop counted in logs.

#### Scenario: Storage failure does not affect the stream

- **WHEN** persisting a live snapshot fails
- **THEN** the proxied response continues unaffected
- **AND** the failure is logged with the account id

#### Scenario: Oversized numeric signal does not affect the stream

- **WHEN** a rate-limit field contains a numeric value too large for a finite float, including a raw JSON integer that exceeds the decoder's conversion limit
- **THEN** the field is treated as unparseable without raising on the serving path

#### Scenario: Queue overflow drops oldest

- **WHEN** the ingest queue is at capacity
- **THEN** the oldest queued snapshot is dropped in favor of the newest

### Requirement: Live writes are throttled per account

Live snapshot writes SHALL be throttled per account by a change fingerprint and a minimum write interval: a snapshot identical to the last persisted one is skipped, and unchanged-window writes within the interval are coalesced. A changed snapshot MAY be written immediately.

#### Scenario: Duplicate snapshots are coalesced

- **WHEN** consecutive turns observe identical rate-limit values within the minimum write interval
- **THEN** at most one usage row set is written

#### Scenario: Changed usage writes promptly

- **WHEN** a snapshot's used percentage or reset timestamp differs from the last persisted values
- **THEN** the write is not deferred by the unchanged-write interval

### Requirement: Live ingestion is decoupled and switchable

The core client layer SHALL publish snapshots through a hub that no-ops until the module layer registers an ingestor at startup. Ingestion SHALL be enabled by default and disableable via `CODEX_LB_LIVE_USAGE_INGESTION_ENABLED`.

#### Scenario: Kill switch disables ingestion

- **WHEN** `CODEX_LB_LIVE_USAGE_INGESTION_ENABLED` is false
- **THEN** proxied responses do not produce usage writes
- **AND** the background poller remains the only usage source

#### Scenario: Unregistered hub is inert

- **WHEN** snapshots are published before an ingestor is registered
- **THEN** they are discarded without error
