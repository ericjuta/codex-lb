# query-caching Delta Specification

## ADDED Requirements

### Requirement: Failed cache invalidation publications are retained and retried

When a cache invalidation publication does not complete because the write raised or the calling task was cancelled, the poller MUST retain the namespace as pending. Its poll loop MUST re-publish each pending namespace on every tick until a write succeeds, and a successful write MUST clear the namespace. The caller of the publication MUST NOT receive the write failure.

#### Scenario: A failed publish is retried on the next poll and peers invalidate
- **GIVEN** a replica committed an API-key mutation and its invalidation write failed
- **WHEN** the replica's poll loop next ticks and the database is reachable
- **THEN** the namespace version is bumped
- **AND** peer replicas observe the new version and run their invalidation callbacks once

#### Scenario: Successful publication leaves nothing pending
- **WHEN** an invalidation write succeeds
- **THEN** no namespace remains pending and peers observe exactly one version bump

### Requirement: Pending invalidation retention is bounded and cancellation-safe

Pending invalidation state MUST be keyed by namespace so repeated failures do not grow it, and retrying MUST NOT spawn additional background tasks. A publication requested while a write is in flight MUST remain pending after that write finishes. Cancellation MUST propagate to the caller only after the namespace is retained.

#### Scenario: Persistent failure stays bounded
- **GIVEN** the database stays unavailable across many ticks and publications
- **THEN** at most one pending entry exists per namespace

#### Scenario: Cancellation retains the namespace
- **WHEN** a publication is cancelled while its write is in progress
- **THEN** the namespace is pending and the cancellation propagates
