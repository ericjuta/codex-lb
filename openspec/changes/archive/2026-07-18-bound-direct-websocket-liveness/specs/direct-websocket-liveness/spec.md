## ADDED Requirements

### Requirement: Direct WebSocket connection establishment is bounded

The service MUST enforce a dedicated total connection-establishment budget for direct upstream Responses WebSockets and MUST bound each upstream open attempt by the lesser of the remaining total budget and a dedicated per-attempt timeout. Selection, credential refresh, and socket-open work MUST NOT extend the total connection-establishment deadline. Both limits SHALL be positive, operator-configurable settings.

#### Scenario: One slow account leaves time for an alternate

- **WHEN** a movable direct WebSocket request selects an account whose upstream open attempt reaches the per-attempt timeout
- **THEN** the first open attempt ends before the total connection-establishment budget expires
- **AND** the service can use the remaining budget to select and open another eligible account

#### Scenario: Attempt timeout is clamped to remaining total budget

- **WHEN** the configured per-attempt timeout exceeds the time remaining in the total connection-establishment budget
- **THEN** the upstream open attempt uses only the remaining total budget
- **AND** the attempt does not extend the total deadline

#### Scenario: Existing request budget remains an outer ceiling

- **WHEN** a request has less time remaining in its existing request budget than the configured direct WebSocket connection budget
- **THEN** connection establishment uses the earlier existing request deadline

### Requirement: Retryable open timeouts immediately use account failover

When a direct upstream WebSocket open fails with `websocket_open_timeout` and is classified as retryable under the same request contract, the service MUST record the account error and MUST NOT retry the same account serially. A movable request MUST release the failed account lease, exclude that account for the current request, and select another eligible account when the attempt count and total connection budget allow. The failover decision log SHALL record action `failover_next` with the request, account, attempt, and failure classification fields.

#### Scenario: Movable request fails over after its first open timeout

- **WHEN** account A times out opening a direct upstream WebSocket and account B is eligible
- **THEN** the service records the timeout against account A
- **AND** the next selection excludes account A
- **AND** the service attempts account B without another open attempt against account A

#### Scenario: Pinned request does not cross accounts

- **WHEN** a direct WebSocket request is pinned to an account by a file reference or `previous_response_id`
- **AND** that account's upstream open attempt times out
- **THEN** the service does not connect the request through another account
- **AND** it returns a structured terminal error through the WebSocket

### Requirement: Exhausted direct WebSocket connection budgets terminate visibly

When the direct WebSocket connection-establishment deadline is exhausted before an upstream socket is established, the service MUST emit a structured retryable terminal error to the downstream WebSocket and MUST persist terminal request-log settlement. It MUST NOT leave the request pending solely because the downstream WebSocket remains open.

#### Scenario: Total connection budget expires

- **WHEN** direct WebSocket selection, refresh, or upstream open work consumes the total connection-establishment budget
- **THEN** the downstream receives the existing structured connection-timeout error
- **AND** the request log is settled with the timeout classification

#### Scenario: No alternate remains after an open timeout

- **WHEN** a retryable upstream open timeout occurs and no eligible alternate account remains
- **THEN** the downstream receives the classified structured upstream error
- **AND** the request log is settled terminally
