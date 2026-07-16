## MODIFIED Requirements

### Requirement: Account leases release on all terminal paths

Every account-local lease acquired for a Responses request MUST be idempotently released or settled on success, upstream error, local startup error, bridge submit failure, startup probe conversion, non-streaming collect completion, failover, downstream disconnect, cancellation, timeout, retry, pending-request teardown, and request-to-connection ownership replacement. A bounded stale-lease watchdog MUST reclaim leases that survive unexpected task cancellation or exceptions, and stale reclamation MUST emit warning/metric evidence. Leases MUST NOT be persisted to the database.

#### Scenario: Lease releases after downstream disconnect

- **WHEN** a streaming `/v1/responses` client disconnects before a terminal upstream event
- **THEN** the account stream lease is released exactly once
- **AND** later routing pressure no longer includes that stream

#### Scenario: WebSocket local account cap releases API-key reservation

- **GIVEN** a WebSocket `response.create` has reserved API-key usage
- **AND** account-local response-create lease acquisition fails with `account_response_create_cap`
- **WHEN** the proxy emits the local terminal failure
- **THEN** the API-key usage reservation is released
- **AND** the pending request is removed from websocket local state

#### Scenario: Stale watchdog recovers orphaned lease

- **WHEN** a request task exits unexpectedly after acquiring an account lease
- **AND** the lease exceeds the configured TTL
- **THEN** the watchdog releases the stale lease
- **AND** emits a low-cardinality warning/metric

#### Scenario: Active stream lease is not reclaimed before valid stream budget

- **GIVEN** a stream lease is older than the base lease TTL
- **AND** the configured Responses stream or HTTP bridge request budget has not elapsed
- **WHEN** account lease stale reclamation runs
- **THEN** the stream lease still counts against account-local stream pressure
- **AND** the proxy does not admit extra streams over the account stream cap by age alone

#### Scenario: Replacing the active WebSocket request releases the previous stream lease

- **GIVEN** a WebSocket connection holds an account stream lease for its active upstream reader
- **AND** the next pending `response.create` owns a reserved account stream lease
- **WHEN** the connection adopts the pending request's lease
- **THEN** the previous connection-owned lease is released before the local lease reference is replaced
- **AND** the adopted lease is removed from pending request state so exactly one owner remains

#### Scenario: Pending WebSocket teardown releases an untransferred stream lease

- **GIVEN** a pending WebSocket request owns a reserved account stream lease that has not transferred to the connection
- **WHEN** disconnect or teardown fails and removes that pending request
- **THEN** the request-owned stream lease is released and cleared exactly once
- **AND** later routing pressure no longer includes that stream
