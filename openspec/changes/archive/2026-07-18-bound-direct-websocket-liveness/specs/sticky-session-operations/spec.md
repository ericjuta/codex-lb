## ADDED Requirements

### Requirement: Retryable websocket open timeouts fail over without rewriting stickiness

When a movable websocket upstream connect attempt fails with a retryable open-handshake timeout (`websocket_open_timeout` with a same-contract retryable classification), the proxy MUST exclude the failed account for the current request and invoke the existing failover ladder without first retrying that account. The exclusion MUST NOT delete or rebind the durable sticky mapping. Requests pinned by file ownership or previous-response continuity MUST NOT cross accounts. The failover decision log line MUST record action `failover_next` alongside the existing request id, transport, account id, attempt, and failure class fields.

#### Scenario: Open timeout moves the current request and preserves sticky affinity

- **GIVEN** a movable websocket request selected its sticky prompt-cache account
- **WHEN** the upstream open handshake times out with a retryable classification
- **THEN** the current request excludes that account and attempts another eligible account
- **AND** the sticky mapping is not reallocated
- **AND** a failover decision with action `failover_next` is logged

#### Scenario: Subsequent request can return to the sticky account

- **GIVEN** a request excluded its sticky account after a transient open timeout
- **WHEN** a subsequent request resolves the same sticky key without that request-scoped exclusion
- **THEN** the original sticky account remains the mapped account

#### Scenario: Continuity owner is not replaced after open timeout

- **GIVEN** a websocket request is pinned to an account by a file reference or `previous_response_id`
- **WHEN** the owner's upstream open handshake times out
- **THEN** the proxy surfaces the terminal connection failure without selecting another account

## REMOVED Requirements

### Requirement: Transient websocket open timeouts retry the same account before breaking stickiness

**Reason**: A full same-account retry doubles the silent failure window and consumes time reserved for an alternate account during upstream edge incidents.

**Migration**: Retryable open timeouts now use immediate request-scoped exclusion and failover while preserving the durable sticky mapping.
