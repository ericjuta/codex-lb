## ADDED Requirements

### Requirement: Estimable context overflow is rejected before upstream connection

The proxy MUST return HTTP 400 with an OpenAI error envelope using code
'context_length_exceeded' and type 'invalid_request_error' when a normalized
Responses request has an estimable inline context whose estimated input tokens
reach the conservative guard limit for the effective model context window.
The rejection MUST occur before admission, account selection, or upstream
connection. The response and logs MUST NOT contain raw prompt text, request
payloads, credentials, or raw session identifiers.

#### Scenario: Spark request is rejected locally

- **GIVEN** the effective context window for 'gpt-5.3-codex-spark' is 128000
- **AND** the normalized inline input estimate reaches the configured guard
  threshold
- **WHEN** a Responses request is received
- **THEN** the proxy returns 400 with 'error.code=context_length_exceeded'
- **AND** no upstream account connection is attempted

#### Scenario: Opaque context is not guessed

- **GIVEN** a request includes a prior-response or conversation anchor, or an
  opaque file/image reference
- **WHEN** the proxy cannot estimate the complete upstream context
- **THEN** the proxy preserves the existing upstream handling path
