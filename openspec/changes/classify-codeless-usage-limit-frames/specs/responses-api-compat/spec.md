## ADDED Requirements

### Requirement: Code-less usage-limit rejections bench the account like the coded form

A failure whose normalized code is `upstream_error` (no upstream code) and whose message states that the account's usage limit has been reached MUST be classified `rate_limit`, MUST bench the serving account, and MUST be eligible for the same pre-visible failover or replay as `usage_limit_reached`. A failure carrying any other code MUST keep that code's classification regardless of its message.

#### Scenario: Code-less stream frame walks the pool and benches the account

- **WHEN** an upstream `response.failed` frame carries only the message "The usage limit has been reached"
- **AND** no output was visible and another account remains
- **THEN** the request is served by the other account
- **AND** the first account is persisted as rate limited.

#### Scenario: Last account is still benched

- **WHEN** the code-less usage-limit frame comes from the only account
- **THEN** the failure is surfaced and the account is persisted as rate limited.

#### Scenario: Pre-created WebSocket frame is replayed

- **WHEN** a pre-created WebSocket `response.failed` or `error` frame carries the usage-limit message without a code
- **THEN** the turn is transparently replayed on another account exactly like the coded form.

#### Scenario: Owner-pinned HTTP stream fails closed with deferred owner health

- **WHEN** a keyed HTTP stream pinned to its `previous_response_id` owner receives the code-less usage-limit frame before any output
- **THEN** the client receives `previous_response_owner_unavailable` exactly as for the coded form
- **AND** the owner's `usage_limit_reached` health write happens only after the API-key reservation settles.

#### Scenario: Echoed sentence under a request-shaped code is not benched

- **WHEN** an `invalid_request_error` rejection quotes the usage-limit sentence
- **THEN** the account MUST NOT be benched.
