## ADDED Requirements

### Requirement: Keyed owner-unavailable streams settle before account health

Default stream API-key reservation settlement MUST continue to await in the request path. Cancellation MAY transfer tracked cleanup without changing that default. This requirement MUST NOT detach ordinary settlement from the response path.

When a keyed websocket stream terminates with an account-health error, when a keyed HTTP SSE failure is rewritten to `previous_response_owner_unavailable`, or when a keyed HTTP SSE terminal queue drains empty before terminal health or success is recorded, the finalizer MUST wait for settlement to commit before the account-health write. If the primary settlement fails, the finalizer MUST wait for fallback release to commit before recording account health. If neither operation confirms settlement, the account-health write and any deferred penalties MUST remain unapplied.

#### Scenario: Websocket health-error settlement precedes the health write

- **GIVEN** a keyed websocket stream that terminates with an account-health error
- **WHEN** the finalizer settles the reservation
- **THEN** it waits for the settlement to commit before recording the account-health error

#### Scenario: Websocket health waits for fallback settlement

- **GIVEN** a keyed websocket stream that terminates with an account-health error
- **AND** its primary settlement fails
- **WHEN** fallback release remains in progress
- **THEN** the finalizer does not record the account-health error
- **AND** it records the error only after fallback release commits

#### Scenario: Unconfirmed websocket settlement leaves health unapplied

- **GIVEN** a keyed websocket stream that terminates with an account-health error
- **WHEN** both primary settlement and fallback release fail
- **THEN** the finalizer does not record the account-health error
- **AND** the upstream connection is still scheduled for reconnect and retirement

#### Scenario: Owner-unavailable rewrite settles before health

- **GIVEN** a keyed HTTP SSE stream rewrites an upstream failure to `previous_response_owner_unavailable`
- **WHEN** the stream records account-health recovery for the original failure
- **THEN** reservation settlement or fail-safe release confirms first

#### Scenario: Empty terminal queue settles before health or success

- **GIVEN** a keyed HTTP SSE bridge queue drains empty on a terminal path
- **WHEN** the stream records terminal account health or success
- **THEN** reservation settlement or fail-safe release confirms first

#### Scenario: Unconfirmed HTTP stream settlement leaves health unapplied

- **GIVEN** a keyed HTTP SSE stream reaches an ordering-sensitive terminal path
- **WHEN** both primary settlement and fallback release fail
- **THEN** the stream does not record account health

#### Scenario: Unconfirmed settlement leaves health unapplied

- **GIVEN** a keyed websocket or HTTP SSE stream reaches an ordering-sensitive terminal path
- **WHEN** both primary settlement and fallback release fail
- **THEN** the stream does not record account health
- **AND** any deferred penalty remains unapplied

#### Scenario: Unconfirmed retry settlement drops deferred health

- **GIVEN** a keyed stream retry has deferred an account-health penalty until replacement selection
- **WHEN** neither primary settlement nor fallback release confirms settlement
- **THEN** the deferred penalty and any immediately following terminal health write remain unapplied
- **AND** the retry path does not start a second settlement for the transferred reservation

#### Scenario: Shutdown drains pending settlements

- **WHEN** the service shuts down gracefully with settlements in flight
- **THEN** shutdown waits for them up to the configured drain timeout
- **AND** a pending ordering-sensitive fallback release remains part of that drain despite cancellation before primary startup or during fallback
