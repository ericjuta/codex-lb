# realtime-api-compat Specification

## Purpose

Define private Codex Live Voice call-owner continuity, authenticated sideband routing, transport privacy, and dashboard/operator contracts without implementing the public OpenAI Realtime API.

## Requirements

### Requirement: Realtime call creation binds the final account under a required proxy key

The proxy SHALL require a registered proxy API key for `POST /backend-api/codex/realtime/calls` even when ordinary proxy API-key authentication is disabled. After upstream success with a supported `Location`, it MUST immutably bind the call to the final ChatGPT account that completed the request.

#### Scenario: initial or replacement account creates the call

- **GIVEN** a registered proxy key and one or more eligible accounts
- **WHEN** the initial account, a pre-visible failover account, or a refreshed account successfully returns `Location: /v1/realtime/calls/rtc_example`
- **THEN** the proxy binds `rtc_example` to the final successful account under that key
- **AND** it returns the upstream status, body, `Location`, and allowlisted response headers unchanged

#### Scenario: call Location carries private query context

- **WHEN** successful call creation returns an exact supported path followed by `?` query text and an optional fragment
- **THEN** the proxy binds only the bounded call id parsed from the path before the first `?`
- **AND** it neither persists nor logs the discarded query or fragment text

#### Scenario: private call creation has no registered key

- **GIVEN** ordinary proxy authentication is disabled
- **WHEN** a caller omits a key or supplies an unregistered key to realtime call creation
- **THEN** the proxy rejects the request before selecting or contacting an upstream account
- **AND** it does not create an anonymous ownership namespace

#### Scenario: successful response cannot be bound

- **WHEN** upstream returns success without a root-relative or absolute `Location` whose parsed path is exactly `/v1/realtime/calls/{bounded_call_id}`, or durable owner binding fails
- **THEN** the proxy returns one `503` with code `realtime_call_binding_failed`
- **AND** it does not expose or replay the already-created upstream call through another account
- **AND** the single private call-creation request row is persisted with error status

#### Scenario: ownership and cleanup remain bounded

- **WHEN** insertion encounters the same digest and owner
- **THEN** it is idempotent
- **WHEN** insertion encounters a different owner for that digest
- **THEN** it preserves the original owner and fails closed
- **WHEN** a binding expires or opportunistic cleanup runs
- **THEN** expiry removal is conditional on the owner and timestamp observed as expired, or cleanup removes one bounded reserved-prefix batch
- **AND** unrelated sticky-session rows remain unchanged

#### Scenario: private freshness diagnostics remain account-safe

- **GIVEN** private call creation reaches account freshness or legacy account-id metadata backfill
- **WHEN** shared refresh cleanup or caller-local metadata persistence emits a warning
- **THEN** the warning contains no internal account identifier, exception text, or traceback
- **AND** shared refresh safety does not depend on whether an ordinary or private caller created the singleflight task

### Requirement: Realtime binding accepts only exact supported Location paths

Realtime binding MUST accept only root-relative or absolute `Location` values with parsed path exactly `/v1/realtime/calls/{call_id}` and a bounded ASCII `rtc_...` or canonical UUID call id. Relative paths without a leading `/`, unrelated prefixes, abbreviated `/live/...` or `/realtime/calls/...` paths, and extra path segments are unsupported.

#### Scenario: Relative Location without a leading slash is unsupported

- **WHEN** successful call creation returns a relative `Location` without a leading `/`
- **THEN** that Location is unsupported for owner binding

### Requirement: Realtime owner bindings persist only bounded private state

The binding MUST be proxy-key-scoped, persist across replicas as only a bounded digest in a reserved non-user-forgeable namespace, and expire after a fixed interval. It MUST NOT persist the raw call id, API key, OAuth token, SDP, attestation value, or frame body.

#### Scenario: Durable owner state excludes raw private material

- **WHEN** a realtime owner binding is persisted
- **THEN** its reserved namespace contains only a bounded digest scoped to the proxy key
- **AND** the binding expires after a fixed interval
- **AND** no raw call id, API key, OAuth token, SDP, attestation value, or frame body is persisted

### Requirement: Private freshness diagnostics apply caller-independent redaction

Private call-creation diagnostics, including caller-local AuthManager metadata work and process-global shared refresh work, MUST redact internal account identifiers and suppress exception details. Shared refresh diagnostics MUST apply this strict policy regardless of the singleflight task's creator.

#### Scenario: Ordinary task creation cannot weaken shared refresh diagnostics

- **WHEN** an ordinary caller creates a shared refresh singleflight task
- **THEN** its diagnostics redact internal account identifiers and suppress exception details under the same strict policy as private callers

### Requirement: Every sideband route uses the exact bound owner without refresh or failover

The proxy SHALL expose `WS /backend-api/codex/{call_id}`, `WS /v1/live/{call_id}`, and `WS /v1/realtime?call_id={call_id}` only to a registered proxy key for its live binding.

#### Scenario: returned Location joins through every supported ingress

- **GIVEN** call creation returned a bound `rtc_...` or canonical UUID id
- **WHEN** the caller opens the current-app path, v3 path, or legacy query route
- **THEN** all three resolve and lease the same immutable owner
- **AND** current-app and v3 use `/v1/live/{call_id}` upstream
- **AND** legacy uses `/v1/realtime?<remaining ordered query>&call_id={call_id}` with one final `call_id`

#### Scenario: unrelated Codex WebSocket path remains outside Live

- **WHEN** a caller opens a one-segment `/backend-api/codex/{value}` path whose value is neither a bounded `rtc_...` id nor a canonical UUID
- **THEN** the dedicated Live route does not match
- **AND** the request remains available to ordinary Codex WebSocket routing

#### Scenario: path ingress also supplies a query call id

- **WHEN** a caller opens the current-app or v3 path with any `call_id` query parameter, whether it matches or conflicts with the path id
- **THEN** the proxy rejects the handshake with `400 invalid_realtime_call_id` before owner resolution or upstream connection
- **AND** it does not silently choose, duplicate, or reorder either id

#### Scenario: caller or owner policy changed

- **WHEN** another key knows the call id, the owner is no longer assigned, or the owner is missing, paused, deleted, capped, or unavailable
- **THEN** attachment fails closed without revealing or substituting the owner
- **AND** it neither refreshes credentials nor selects another account

#### Scenario: refreshed call owner attaches with current identity

- **GIVEN** call creation refreshed and persisted the final owner's token or identity while routing inputs remained cached
- **WHEN** the sideband attaches
- **THEN** the service fresh-loads that same leased owner from persistence
- **AND** the connector uses the current persisted bearer, account, installation, and route identity
- **AND** the stream lease is released exactly once

### Requirement: Sideband adapters share owner attachment services

All sideband adapters MUST share one bounded call-id normalizer, current key-assignment check, exact-owner selection, fresh owner load, reattach stream lease, relay, and connector service.

#### Scenario: Every ingress uses the shared owner attachment path

- **WHEN** a supported sideband ingress attaches to a bound call
- **THEN** it uses the shared normalizer, current assignment check, exact-owner selection, fresh owner load, lease, relay, and connector service

### Requirement: Sideband ingress preserves route-specific call-id handling

Current-app and v3 ingress MUST reject any downstream `call_id` query parameter before entering the live service or connector. They MUST NOT reconcile it with the path id and MUST connect upstream to `/v1/live/{call_id}`. Legacy ingress MUST consume exactly one downstream `call_id` and append its normalized value once after remaining ordered query pairs to `/v1/realtime`.

#### Scenario: Legacy ingress appends one normalized call id

- **WHEN** legacy ingress consumes its single downstream `call_id`
- **THEN** it connects to `/v1/realtime` with the normalized value appended once after the remaining ordered query pairs

### Requirement: Realtime forwarding preserves protocol context, privacy, and deterministic ownership

The live connector MUST replace downstream proxy authorization, account identity, and client-supplied installation identity with the bound owner identity. It MUST apply existing egress policy.

#### Scenario: protocol-faithful handshake

- **WHEN** a live caller supplies supported query and context headers
- **THEN** upstream receives those values in their required order with bound-owner credentials
- **AND** it does not receive the downstream proxy bearer, client installation identity, duplicate call id, Responses beta, or synthesized subprotocol
- **AND** any ordered subprotocol offers are negotiated upstream without a raw duplicated header
- **AND** downstream receives only the upstream-selected offered value, or no value when upstream selects none

#### Scenario: definitive denial and proxy errors remain isolated

- **WHEN** routed upstream returns a definitive handshake status
- **THEN** the proxy preserves the normalized status without route or credential details and does not replay the denial
- **WHEN** the live connector raises `InvalidProxy`, `InvalidHandshake`, or `OSError`
- **THEN** the sideband receives a fixed capability-specific, credential-safe message
- **AND** the Responses WebSocket connector returns the same fixed credential-safe message for `InvalidProxy`, logging only the connector's URL-free reason, while its `InvalidHandshake` and `OSError` behavior remains unchanged

#### Scenario: either peer disconnects or connection is cancelled

- **WHEN** a peer closes, a paired relay finishes, or the handler/connection attempt is cancelled
- **THEN** the opposite peer receives only a valid bounded close code/reason when available
- **AND** paired work is cancelled and awaited
- **AND** each peer, connector, and stream lease is released at most once
- **AND** a close task that ignores cancellation is awaited only through a fixed post-cancel drain cap before lease release continues

#### Scenario: diagnostics remain content-free

- **GIVEN** payload tracing and Responses frame archiving are enabled
- **WHEN** call creation carries SDP or the sideband carries realtime frames
- **THEN** SDP and frame bodies are absent from traces and archives
- **AND** sideband rows use `request_kind=realtime_live`, `transport=websocket`, and a redacted path
- **AND** persisted private call-creation and sideband rows omit account identity, model content, upstream error text, failure metadata, live query text, and credentials

### Requirement: Realtime forwarding preserves context without synthesizing negotiation headers

The live connector MUST preserve remaining ordered query pairs and supplied version-specific alpha value or absence, FedRAMP, residency, session/context, originator, and attestation headers. It MUST strip Responses-only beta values and synthesize neither `OpenAI-Beta` nor `Sec-WebSocket-Protocol`.

#### Scenario: Missing negotiation headers stay absent

- **WHEN** a live caller supplies neither an alpha value nor WebSocket subprotocol offers
- **THEN** forwarding preserves the alpha absence and synthesizes neither `OpenAI-Beta` nor `Sec-WebSocket-Protocol`

### Requirement: Realtime subprotocol negotiation preserves upstream selection

The live connector MUST pass exact ordered downstream WebSocket subprotocol offers through the transport negotiation API. It MUST accept downstream only with an upstream-selected value offered downstream, or no selection when upstream selects none.

#### Scenario: Upstream selects no subprotocol

- **WHEN** upstream selects none of the downstream WebSocket subprotocol offers
- **THEN** downstream acceptance preserves no subprotocol selection

### Requirement: Realtime relay and cleanup remain bounded

The live connector MUST relay text and binary messages without interpretation, preserve only bounded valid close data, enforce the existing message-size boundary, and close/cancel/await each owned peer or task at most once. Initial upstream close and post-cancel drain MUST be bounded. Cancellation-resistant cleanup MUST NOT delay handler completion or stream-lease release. Any eventual late task result MUST be consumed without exposing details.

#### Scenario: Late cleanup results remain private

- **WHEN** cancellation-resistant upstream cleanup exceeds its bounded drain and later completes
- **THEN** handler completion and stream-lease release proceed without waiting indefinitely
- **AND** the eventual task result is consumed without exposing details

### Requirement: Internal ownership and request logs honor dashboard contracts

Reserved realtime ownership is internal continuity state. Ordinary sticky-session operator APIs MUST hide it and MUST NOT delete it through single, bulk, filtered, or delete-all operations. The dashboard `RequestLogsResponseSchema` MUST accept full persisted request rows with `requestKind=realtime_live` and `transport=websocket`. It MUST retain a closed request-kind enum, not arbitrary strings.

#### Scenario: reserved owner is not an operator session

- **GIVEN** reserved realtime ownership and ordinary sticky-session rows exist
- **WHEN** an operator lists sessions or performs single, bulk, filtered, or delete-all cleanup
- **THEN** reserved rows are absent from list results and remain unchanged
- **AND** ordinary matching rows retain their existing behavior

#### Scenario: Recent Requests consumes a live sideband row

- **GIVEN** the backend returns a full persisted request row with `requestKind: "realtime_live"` and `transport: "websocket"`
- **WHEN** the dashboard parses the response
- **THEN** parsing succeeds with the typed `realtime_live` value preserved

### Requirement: Private realtime compatibility preserves zero-config base behavior and public boundaries

The capability MUST use existing configuration and key registration. User documentation MUST describe these routes as private Codex app compatibility, not advertise a public Realtime API. Private routes require a registered key. The untouched base proxy and dashboard MUST start and operate with zero new setup.

#### Scenario: operator does not use Live Voice

- **WHEN** an operator starts the base proxy and dashboard without adding configuration for this capability
- **THEN** existing startup and ordinary proxy/dashboard behavior remain available
- **AND** no public model or documented public Realtime route advertises this private transport

### Requirement: Private realtime compatibility adds no setup or public API surface

The capability MUST add no setting, migration, dependency, dashboard navigation item, README section, `.env.example` line, public model entry, public `/v1/realtime/calls`, or public `/v1/realtime/client_secrets` implementation.

#### Scenario: Private compatibility does not implement public call creation

- **WHEN** private realtime compatibility is available
- **THEN** it adds neither a public `/v1/realtime/calls` nor a public `/v1/realtime/client_secrets` implementation
