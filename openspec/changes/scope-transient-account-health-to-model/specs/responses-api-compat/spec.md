## MODIFIED Requirements

### Requirement: Pre-commit ambiguous websocket 403 failures fail over by account

Before a Responses path emits downstream bytes, events, or frames, ambiguous upstream websocket-connect `403` MUST be treated as account-scoped failure, not immediately surfaced. Retries MUST retain the upstream transport family. The service MUST NOT downgrade to HTTP solely because of that `403`. The resulting cooldown MUST apply to selecting the account for the requested model when the model is known, and to the whole account otherwise.

#### Scenario: Websocket connect 403 fails over to another eligible account

- **WHEN** the proxy selects an account for a Responses request that requires an upstream websocket connect
- **AND** the upstream websocket connect fails with HTTP `403`
- **AND** the failure does not carry a permanent deactivation signal
- **AND** the proxy has not yet emitted any downstream bytes, events, or frames
- **AND** another eligible account exists
- **THEN** the proxy places the failed account into a temporary runtime cooldown for websocket-connect selection of the requested model
- **AND** it retries the same request against another eligible account on the same transport family
- **AND** it does not silently downgrade to HTTP only because of that `403`

#### Scenario: Final ambiguous websocket connect 403 remains visible

- **WHEN** a pre-commit upstream websocket connect fails with HTTP `403`
- **AND** no other eligible account can serve the request
- **THEN** the proxy surfaces the final upstream `403` to the client
- **AND** the proxy records the failure as a client-exposed pre-commit upstream error

#### Scenario: Connect 403 cooldown leaves other models selectable

- **GIVEN** an upstream websocket connect for model A failed with HTTP `403` on an account
- **WHEN** a request for model B runs account selection during the cooldown
- **THEN** the account is eligible for model B
