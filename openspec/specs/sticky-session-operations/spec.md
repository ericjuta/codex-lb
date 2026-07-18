# sticky-session-operations Specification

## Purpose

Define sticky-session operation contracts so durable sessions, dashboard affinity, and prompt-cache affinity stay distinct.
## Requirements
### Requirement: Sticky sessions are explicitly typed
The system SHALL persist each sticky-session mapping with an explicit kind so durable Codex backend affinity, durable dashboard sticky-thread routing, and bounded prompt-cache affinity can be managed independently.

#### Scenario: Backend Codex session affinity is stored as durable
- **WHEN** a backend Codex request creates or refreshes stickiness from `session_id`
- **THEN** the stored mapping kind is `codex_session`

#### Scenario: Backend Codex session rebinds under budget pressure
- **WHEN** a backend Codex request resolves an existing `codex_session` mapping
- **AND** the pinned account is above the configured sticky reallocation budget threshold
- **AND** another eligible account remains below that threshold
- **THEN** selection rebinds the durable `codex_session` mapping to the healthier account before sending the request upstream

#### Scenario: Dashboard sticky thread routing is stored as durable
- **WHEN** sticky-thread routing creates or refreshes stickiness from a prompt-derived key
- **THEN** the stored mapping kind is `sticky_thread`

#### Scenario: OpenAI prompt-cache affinity is stored as bounded
- **WHEN** an OpenAI-style request creates or refreshes prompt-cache affinity
- **THEN** the stored mapping kind is `prompt_cache`

#### Scenario: Identical keys remain isolated across sticky-session kinds
- **WHEN** the same sticky-session key value is used for more than one kind
- **THEN** each `(key, kind)` mapping is stored and managed independently without overwriting the others

#### Scenario: Dashboard sticky thread rebinds under budget pressure
- **WHEN** a request resolves an existing `sticky_thread` mapping
- **AND** the pinned account is otherwise eligible to serve traffic
- **AND** the pinned account is strictly above the configured sticky reallocation budget threshold
- **AND** another eligible account remains at or below that threshold
- **THEN** selection rebinds the durable `sticky_thread` mapping to the healthier account before sending the request upstream

#### Scenario: Dashboard sticky thread is preserved when every candidate is above the threshold
- **WHEN** a request resolves an existing `sticky_thread` mapping
- **AND** the pinned account is otherwise eligible to serve traffic
- **AND** the pinned account is strictly above the configured sticky reallocation budget threshold
- **AND** every other eligible account is also strictly above that threshold
- **THEN** selection retains the existing pinned account to avoid sticky-pin thrashing

### Requirement: Dashboard exposes sticky-session administration
The system SHALL provide dashboard APIs for listing sticky-session mappings, deleting one mapping, and purging stale mappings.

#### Scenario: List sticky-session mappings
- **WHEN** the dashboard requests sticky-session entries
- **THEN** the response includes each mapping's `key`, `account_id`, `kind`, `created_at`, `updated_at`, `expires_at`, and `is_stale`
- **AND** the response includes the total number of stale `prompt_cache` mappings that currently exist beyond the returned page

#### Scenario: List only stale mappings
- **WHEN** the dashboard requests sticky-session entries with `staleOnly=true`
- **THEN** the system applies stale prompt-cache filtering before enforcing the result limit

#### Scenario: Delete one mapping
- **WHEN** the dashboard deletes a sticky-session mapping by both `key` and `kind`
- **THEN** the system removes that mapping and returns a success response

#### Scenario: Purge stale prompt-cache mappings
- **WHEN** the dashboard requests a stale purge
- **THEN** the system deletes only stale `prompt_cache` mappings and leaves durable mappings untouched

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

### Requirement: Soft bridge affinity can reroute under local pressure

Prompt-cache and sticky-thread bridge affinity that does not carry a hard continuity dependency MUST be treated as soft. A client-supplied or proxy-derived `prompt_cache_key` is a cache-locality hint, not a correctness dependency; the proxy MAY reroute it under local pressure and accept lower cache-hit rates. When the preferred soft bridge session is saturated by queue depth, response-create gate pressure, bridge capacity, or account-local caps, the service MUST evaluate other eligible accounts/sessions before returning a local overload response. The service MUST emit internal diagnostics such as `internal_soft_affinity_reroute` for successful reroutes without adding those diagnostic names to the stable failure taxonomy.

#### Scenario: Prompt-cache bridge queue reroutes to an eligible account

- **GIVEN** a prompt-cache request's preferred bridge session queue is full
- **AND** another eligible account/session is below cap
- **WHEN** the request has no hard previous-response or turn-state continuity dependency
- **THEN** the proxy routes to the alternate account/session
- **AND** records an internal soft-affinity reroute diagnostic

#### Scenario: Prompt cache key does not override hard previous-response continuity

- **GIVEN** a `/v1/responses` request carries both `previous_response_id` and `prompt_cache_key`
- **AND** the previous response owner is known
- **WHEN** the prompt-cache preferred account differs from the previous-response owner
- **THEN** the proxy treats the request as hard owner-bound to the previous-response owner
- **AND** it does not route to the prompt-cache account when that account cannot preserve the stored response continuation

### Requirement: Hard continuity remains owner-bound and bounded

Requests that depend on `previous_response_id`, hard turn-state, account-scoped `input_file.file_id` pins, or another required owner continuity source MUST NOT silently reroute to an account that cannot preserve continuity. A `previous_response_id` is a stored-object continuation reference and remains owner-bound even when the same request also carries `prompt_cache_key` or another soft locality key. If the owner account/session is unavailable or saturated, the service MUST fail closed with an explicit retryable continuity/local overload reason instead of flooding the owner queue indefinitely.

#### Scenario: Previous-response owner queue is saturated

- **WHEN** a `/v1/responses` follow-up requires a previous-response owner
- **AND** the owner session queue or account cap is saturated
- **THEN** the service fails closed with `hard_affinity_saturated` or `previous_response_owner_unavailable`
- **AND** it does not route to an unrelated account that lacks continuity state

#### Scenario: File-pinned request owner is capped

- **WHEN** a `/v1/responses` request references an `input_file.file_id` pinned to an owner account
- **AND** the owner account is at its account stream or response-create cap
- **THEN** the service returns a local account-cap overload for the owner
- **AND** it does not route the file reference to another account

### Requirement: WebSocket continuity state rows are pruned proactively
The system SHALL prune persisted WebSocket continuity state rows older than
48 hours as part of the existing leader-elected background cleanup loop, and
the pruning step SHALL be guarded so that its failure — including the
`websocket_continuity_states` table not existing yet mid-rollout — does not
prevent the loop's other cleanup steps from running.

#### Scenario: Cleanup loop removes stale continuity rows
- **WHEN** the cleanup loop runs and finds `websocket_continuity_states` rows
  with `updated_at` older than 48 hours
- **THEN** it deletes those rows
- **AND** rows updated within the last 48 hours survive

#### Scenario: Missing continuity table does not break the loop
- **WHEN** the cleanup loop runs before the continuity-state migration has
  been applied
- **THEN** the continuity pruning step fails quietly
- **AND** the prompt-cache and bridge-session purges in the same loop still
  run

### Requirement: Retryable websocket open timeouts fail over without rewriting stickiness

When a movable websocket upstream connect attempt fails with a retryable open-handshake timeout (`websocket_open_timeout` with a same-contract retryable classification), the proxy MUST exclude the failed account for the current request and invoke the existing failover ladder without first retrying that account. The exclusion MUST NOT delete or rebind the durable sticky mapping. Requests pinned by file ownership or previous-response continuity MUST NOT cross accounts. The failover decision log line MUST record action `failover_next` alongside the existing request id, transport, account id, attempt, and failure class fields.

#### Scenario: Open timeout moves the current request and preserves sticky affinity

- **GIVEN** a movable websocket request selected its sticky prompt-cache account
- **WHEN** the upstream open handshake times out with a retryable classification
- **THEN** the current request excludes that account and attempts another eligible account
- **AND** the sticky mapping is not reallocated
- **AND** a failover decision with action `failover_next` is logged

#### Scenario: Subsequent request can return to the sticky account

- **GIVEN** a request excluded its sticky account after a transient open timeout
- **WHEN** a subsequent request resolves the same sticky key without that request-scoped exclusion
- **THEN** the original sticky account remains the mapped account

#### Scenario: Continuity owner is not replaced after open timeout

- **GIVEN** a websocket request is pinned to an account by a file reference or `previous_response_id`
- **WHEN** the owner's upstream open handshake times out
- **THEN** the proxy surfaces the terminal connection failure without selecting another account

### Requirement: Per-request account exclusion preserves sticky mappings

When account selection resolves an existing sticky mapping whose pinned account is absent from the candidate pool solely because it was excluded for the current request (for example transport failover after a connect failure), the system MUST select a fallback account for that request without deleting or rewriting the sticky mapping, for every sticky-session kind. Sticky mappings SHALL only be deleted or rebound by pool-membership changes (account removed or out of scope), permanent account status, budget-pressure reallocation, TTL expiry, or explicit administrative action.

#### Scenario: Transport failover keeps the prompt-cache mapping

- **GIVEN** a `prompt_cache` mapping pinned to account A
- **WHEN** a request excludes account A after a transient connect failure and selection reallocates
- **THEN** a fallback account serves the request
- **AND** the `prompt_cache` mapping still points at account A
- **AND** a subsequent request without the exclusion returns to account A

#### Scenario: Transport failover keeps the durable codex-session mapping

- **GIVEN** a `codex_session` mapping pinned to account A
- **WHEN** a request excludes account A after a transient connect failure and selection reallocates
- **THEN** a fallback account serves the request
- **AND** the `codex_session` mapping still points at account A

#### Scenario: Pinned account removed from the pool still deletes the mapping

- **GIVEN** a sticky mapping pinned to an account that has been deleted or moved out of the API-key scope
- **WHEN** selection resolves the mapping and the account is not in the candidate pool for a non-exclusion reason
- **THEN** the stale mapping is deleted and the fallback placement is persisted

### Requirement: Sticky selection outcomes are observable

The system MUST record a sticky-selection outcome metric (`codex_lb_sticky_selection_total`) labeled by sticky kind and outcome for every selection that carries a sticky key, with outcomes distinguishing at least: pinned account selected (`hit`), fallback without mapping mutation (`fallback`), fallback persisted over an existing mapping (`rebind`), and first placement (`new`). The metric MUST be a no-op when the metrics backend is unavailable.

#### Scenario: Pinned selection increments hit

- **WHEN** selection returns the account already stored in the sticky mapping
- **THEN** the counter increments with outcome `hit` and the mapping's kind label

#### Scenario: Preserved fallback increments fallback

- **WHEN** selection returns a different account while preserving the existing mapping
- **THEN** the counter increments with outcome `fallback`

#### Scenario: Persisted rebind increments rebind

- **WHEN** selection persists a fallback account over an existing mapping
- **THEN** the counter increments with outcome `rebind`

#### Scenario: First placement increments new

- **WHEN** selection creates a sticky mapping where none existed
- **THEN** the counter increments with outcome `new`
