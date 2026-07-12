# Delta: sticky-session-operations

## ADDED Requirements

### Requirement: Transient websocket open timeouts retry the same account before breaking stickiness

When a websocket upstream connect attempt fails with a retryable open-handshake timeout (`websocket_open_timeout` with a same-contract retryable classification), the proxy MUST retry the same account once before excluding it and reallocating sticky affinity, provided the request budget allows another attempt. The retry MUST NOT mark the account excluded and MUST NOT reallocate the sticky mapping. At most one same-account retry SHALL be performed per account per request; a second open timeout on the same account MUST fall back to the existing failover ladder (exclude and reallocate). The failover decision log line MUST record the same-account retry with a distinct action value (`retry_same_account`) alongside the existing request id, transport, account id, attempt, and failure class fields.

#### Scenario: Open timeout retries same account and preserves sticky affinity

- **GIVEN** a websocket request selected its sticky prompt-cache account
- **WHEN** the upstream open handshake times out once
- **AND** the retry against the same account connects successfully
- **THEN** the request proceeds on the original sticky account
- **AND** the sticky mapping is not reallocated
- **AND** a failover decision with action `retry_same_account` is logged

#### Scenario: Repeated open timeout falls back to failover

- **GIVEN** a websocket request already consumed its same-account retry for the selected account
- **WHEN** the retry attempt also times out during the open handshake
- **THEN** the proxy excludes the account and reallocates using the existing failover ladder

#### Scenario: Non-timeout failures do not get a same-account retry

- **WHEN** a websocket upstream connect attempt fails with a non-timeout retryable failure (for example an upstream 403 or close code)
- **THEN** the proxy applies the existing failover ladder without a same-account retry

#### Scenario: Exhausted budget skips the same-account retry

- **WHEN** the open handshake times out and the remaining request budget cannot cover another connect attempt
- **THEN** the proxy does not retry the same account and follows the existing failover/surface behavior

## MODIFIED Requirements

### Requirement: Prompt-cache mappings are cleaned up proactively
The system SHALL run a background cleanup loop that deletes stale `prompt_cache` mappings using the current dashboard prompt-cache affinity TTL. The same loop SHALL delete `codex_session` mappings whose `updated_at` is older than a configurable retention window (default 30 days); a retention setting of `0` SHALL disable the `codex_session` purge. The purge step SHALL be guarded so its failure does not prevent the loop's other cleanup steps from running.

#### Scenario: Cleanup loop removes stale prompt-cache mappings
- **WHEN** the cleanup loop runs and finds `prompt_cache` mappings older than the configured TTL
- **THEN** it deletes those mappings

#### Scenario: Cleanup loop removes aged codex_session mappings
- **WHEN** the cleanup loop runs and finds `codex_session` mappings with `updated_at` older than the configured retention window
- **THEN** it deletes those mappings
- **AND** `codex_session` mappings updated within the retention window survive

#### Scenario: Retention setting of zero disables codex_session purge
- **WHEN** the `codex_session` retention setting is `0`
- **THEN** the cleanup loop does not delete any `codex_session` mappings regardless of age

#### Scenario: Cleanup loop preserves sticky_thread mappings
- **WHEN** the cleanup loop runs
- **THEN** it does not delete `sticky_thread` mappings regardless of age
