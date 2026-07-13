## MODIFIED Requirements

### Requirement: Estimable context overflow is rejected before upstream connection

The proxy MUST return HTTP 400 with an OpenAI error envelope using code
'context_length_exceeded' and type 'invalid_request_error' when a normalized
Responses request has an estimable inline context whose estimated input tokens
reach the conservative guard limit for the effective model context window.
The rejection MUST occur before admission, account selection, or upstream
connection. Opaque prior-response, conversation, and file/image contexts MAY
remain on the existing upstream handling path when their complete size is not
locally knowable. A well-formed compaction-lane request — one whose final
top-level input item is a single terminal `compaction_trigger` — MUST bypass
the guard on every guarded path (HTTP stream, HTTP collect, and websocket
`response.create`) so that remote-compaction recovery is never rejected by the
guard it is recovering from. Malformed trigger placement MUST NOT receive the
exemption.

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

#### Scenario: Compaction-lane request bypasses the guard

- **GIVEN** a Responses request whose estimated inline input reaches the guard
  threshold
- **AND** its final top-level input item is a single `compaction_trigger`
- **WHEN** the request is received on the HTTP or websocket responses path
- **THEN** the guard does not reject the request
- **AND** the request proceeds to compaction handling

#### Scenario: Malformed trigger placement is not exempt

- **GIVEN** a Responses request whose estimated inline input reaches the guard
  threshold
- **AND** it contains a `compaction_trigger` that is duplicated or not the
  final top-level input item
- **WHEN** the request is received
- **THEN** the request does not receive the guard exemption
