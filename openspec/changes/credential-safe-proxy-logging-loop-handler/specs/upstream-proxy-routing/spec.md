## ADDED Requirements

### Requirement: Dashboard rejects and reports proxy usernames the resolver cannot encode

The dashboard MUST reject an `http` or `https` upstream proxy endpoint whose
username contains `:` at creation with a 400 error coded `invalid_proxy_username`,
mirroring the resolver rule (RFC 7617 Basic credentials cannot encode a colon
in the user-id). SOCKS5/SOCKS5H RFC 1929 usernames MAY contain `:`. The
endpoint test route MUST report a resolver rejection of an already persisted
endpoint as a failed probe carrying the resolver reason rather than surfacing
an unhandled error.

#### Scenario: HTTP colon username is rejected at creation

- **WHEN** an operator creates an `http` or `https` upstream proxy endpoint whose username contains `:`
- **THEN** the request is rejected with a 400 error coded `invalid_proxy_username`

#### Scenario: SOCKS colon username is accepted at creation

- **WHEN** an operator creates a `socks5` or `socks5h` upstream proxy endpoint whose username contains `:`
- **THEN** the endpoint is created and the username is preserved

#### Scenario: Endpoint test reports a persisted row the resolver rejects

- **GIVEN** a persisted endpoint the resolver rejects (for example a username containing `:`)
- **WHEN** the endpoint test route is invoked for it
- **THEN** the response reports `ok: false` with the resolver reason as `error` and no status code
- **AND** no probe is sent
