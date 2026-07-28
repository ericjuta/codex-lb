## ADDED Requirements

### Requirement: Fresh durable HTTP bridge preserves safe client-unanchored full resends

The service MUST preserve a client-unanchored full resend as the first request on a fresh durable HTTP bridge when the request resolves a hard durable conversation, has no client-supplied `previous_response_id`, exactly matches the stored durable input prefix, and has neither a reusable local bridge nor a forwardable remote owner. After response-owned bookkeeping is removed, the resend suffix MUST either retain completed assistant output before fresh user input or consist only of complete direct tool call/output pairs that exactly settle the durable prior-response tool-call manifest.

The durable manifest MUST include every observed supported direct tool-call `response.output_item.added` event, MUST require one matching `response.output_item.done` event with the same call ID and type, and MUST reconcile tool calls present in terminal response output. An incomplete, conflicting, duplicated, malformed, or unsupported lifecycle MUST persist an unknown manifest rather than a partial manifest. A manifest MUST be bound to the exact durable response ID, and readers MUST treat a response-ID mismatch as unknown.

For a proven safe resend, the service MUST submit the original input without adding `previous_response_id`, MUST retain the durable preferred account and hard affinity, MUST NOT move the request through account-neutral replay, and MUST NOT trim the stored prefix before the first send. The service MUST NOT seed the new local session with the old durable response in a way that re-injects the anchor before submission.

For a resend that omits prior output, contains an incomplete or orphaned tool sequence, omits any durable call, reuses a stored-prefix call ID, has no known manifest where a manifest is required, or otherwise fails the proof, the service MUST retain existing durable-anchor injection and verified-prefix trimming behavior. Client-supplied anchors, owner-forward recovery, and live-session continuation behavior MUST remain unchanged.

#### Scenario: Retained assistant output opens a fresh bridge without an anchor

- **GIVEN** a client-unanchored full resend exactly matches the durable stored prefix and retains completed assistant output before fresh user input
- **AND** no reusable local bridge or forwardable remote owner exists
- **WHEN** the service creates a fresh upstream WebSocket on the durable owner
- **THEN** the first `response.create` omits `previous_response_id`
- **AND** the request contains the original untrimmed input and retains hard affinity

#### Scenario: Exact direct tool loop opens a fresh bridge without an anchor

- **GIVEN** the durable prior-response manifest is known
- **AND** the verified resend suffix contains one complete direct call/output pair for every manifest entry and no other items
- **WHEN** the service creates a fresh upstream WebSocket on the durable owner
- **THEN** it submits the original unanchored request once on that owner

#### Scenario: Omitted parallel call remains anchored

- **GIVEN** the durable manifest contains two parallel call IDs
- **WHEN** the resend settles only one call ID
- **THEN** the service retains the durable `previous_response_id` and trims the verified stored prefix

#### Scenario: Retained output is missing

- **GIVEN** a cumulative prompt matches the durable stored prefix but omits completed assistant output
- **WHEN** no reusable bridge exists
- **THEN** the service retains the durable `previous_response_id` and trims the verified stored prefix

#### Scenario: Incomplete lifecycle keeps the manifest unknown

- **GIVEN** a response emits added events for two direct tool calls
- **AND** only one call reaches a matching done event before completion
- **WHEN** the durable alias is persisted
- **THEN** the durable manifest is unknown rather than a one-call partial manifest

#### Scenario: Unsupported client-settled call keeps the manifest unknown

- **GIVEN** a response emits a supported direct call and a parallel `computer_call` or `mcp_approval_request`
- **WHEN** the durable alias is persisted
- **THEN** the durable manifest is unknown rather than a partial supported manifest

#### Scenario: Duplicate lifecycle ID keeps the manifest unknown

- **GIVEN** a call ID appears more than once in added, done, or terminal output lifecycle data
- **WHEN** the durable alias is persisted
- **THEN** the durable manifest is unknown even when the duplicate types match

#### Scenario: Legacy row remains anchored

- **GIVEN** a durable row predates the manifest migration or contains malformed manifest data
- **WHEN** a matching resend contains only direct call/output pairs
- **THEN** the service retains the durable `previous_response_id`

#### Scenario: Older writer advances the response

- **GIVEN** a durable row contains a response-bound manifest
- **WHEN** another writer advances `latest_response_id` without a matching manifest update
- **THEN** readers treat the stale manifest as unknown and later direct tool-loop resends remain anchored

#### Scenario: Stored-prefix call ID is reused

- **GIVEN** the verified stored prefix already contains a call ID from the durable manifest
- **WHEN** a resend suffix attempts to settle that same ID
- **THEN** the service rejects the unanchored proof and retains anchored behavior

#### Scenario: Live bridge behavior is unchanged

- **GIVEN** the durable conversation still has a reusable live bridge
- **WHEN** a verified full resend continues that session
- **THEN** existing session-level anchor injection and prefix trimming remain available
