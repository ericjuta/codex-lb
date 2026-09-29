## ADDED Requirements

### Requirement: File operation failover honors typed transport provenance

For `POST /backend-api/files` and `POST /backend-api/files/{file_id}/uploaded`, the proxy MUST preserve typed routed-transport failure phase, error code, and replay eligibility from the file client through the service failover decision.

Rules:
- A typed transport failure proven to occur before dispatch MUST use the existing previsible unary account failover policy, even when its credential-safe message contains no transient-error phrase.
- Typed transport failures MUST NOT gain replay eligibility from message text.
- TLS verification failures, ambiguous request failures, response-body failures, and process-wide network failures MUST NOT invoke the file operation through another account.
- Process-wide network failures MUST keep the `proxy_network_unavailable` error code.
- Transport failures without typed provenance MUST keep the existing message-based classification.
- File-finalize requests pinned to the account that registered the file MUST NOT be sent through another account.

#### Scenario: Routed pre-dispatch refusal on file create uses another account

- **GIVEN** an unpinned file-create request and another eligible account
- **WHEN** the selected account's routed proxy connection is refused before dispatch
- **THEN** the proxy excludes the failed account and completes file create through the eligible fallback account within the request budget
- **AND** the created `file_id` is pinned to the fallback account

#### Scenario: Routed pre-dispatch refusal on the first finalize poll uses another account

- **GIVEN** an unpinned file-finalize request, another eligible account, and no finalize poll response yet
- **WHEN** the first routed poll's proxy connection is refused before dispatch
- **THEN** the proxy completes finalization through the eligible fallback account within the request budget

#### Scenario: Unsafe routed file failures do not replay

- **GIVEN** an unpinned routed file-create or file-finalize request and another eligible account
- **WHEN** the transport reports a TLS verification failure, an ambiguous request failure, or a response-body failure
- **THEN** the proxy returns HTTP 502 with error code `upstream_unavailable`
- **AND** the proxy invokes no upstream file operation through another account

#### Scenario: Process-wide network failure stays account-neutral

- **GIVEN** an unpinned routed file-create or file-finalize request and another eligible account
- **WHEN** the routed transport reports a process-wide network failure
- **THEN** the proxy returns HTTP 502 with error code `proxy_network_unavailable`
- **AND** the proxy invokes no upstream file operation through another account

#### Scenario: Pinned finalize fails closed

- **GIVEN** a file-finalize request pinned to the account that registered the file
- **WHEN** a finalize poll fails before dispatch with a replay-eligible transport failure
- **THEN** the proxy returns an error without invoking a finalize poll through another account

### Requirement: File finalization transport failures do not fail over after a poll response

Once any upstream `POST /files/{file_id}/uploaded` poll for a finalize request returns an HTTP response, the proxy MUST treat every later transport failure of that request as not eligible for transport-failure account failover. The proxy MUST NOT use a later transport failure to invoke finalization through another account. This rule MUST hold for both account-routed proxy transport and direct upstream transport. It MUST NOT change the existing `401` forced-refresh and account-reselection path, and pinned finalize ownership MUST remain enforced.

#### Scenario: Routed later poll refusal stays on the first account

- **GIVEN** an unpinned file-finalize request whose first routed poll returned `status: retry`
- **WHEN** a later routed poll's proxy connection is refused before dispatch
- **THEN** the proxy returns HTTP 502 with error code `upstream_unavailable`
- **AND** every finalize poll for the request used the first account

#### Scenario: Direct later poll connection failure stays on the first account

- **GIVEN** an unpinned file-finalize request whose first direct poll returned `status: retry`
- **WHEN** a later direct poll fails with a connection error whose message looks transient
- **THEN** the proxy returns HTTP 502 with error code `upstream_unavailable`
- **AND** every finalize poll for the request used the first account

#### Scenario: Direct first poll connection failure keeps legacy failover

- **GIVEN** an unpinned file-finalize request, another eligible account, and no direct finalize poll response yet
- **WHEN** the first direct poll fails with a transient-looking connection error
- **THEN** the proxy completes finalization through the eligible fallback account within the request budget
