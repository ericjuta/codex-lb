# sticky-session-operations Specification

## Purpose

Define sticky-session operation contracts so durable sessions, dashboard affinity, and prompt-cache affinity stay distinct.
## Requirements
### Requirement: Sticky sessions are explicitly typed
The system SHALL persist each sticky-session mapping with an explicit kind to manage durable Codex backend affinity, durable dashboard sticky-thread routing, and bounded prompt-cache affinity independently.

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
The background cleanup loop SHALL delete stale `prompt_cache` mappings using the current dashboard prompt-cache affinity TTL. It SHALL also delete `codex_session` mappings whose `updated_at` is older than a configurable retention window (default 30 days). A retention setting of `0` SHALL disable that purge. The purge SHALL be guarded so failure does not prevent other cleanup steps.

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

Prompt-cache and sticky-thread bridge affinity without hard continuity dependencies MUST be treated as soft. A client-supplied or proxy-derived `prompt_cache_key` is a cache-locality hint, not a correctness dependency. The proxy MAY reroute it under local pressure and accept lower cache-hit rates.

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

### Requirement: Soft bridge saturation evaluates alternatives before overload

When queue depth, response-create gate pressure, bridge capacity, or account-local caps saturate a preferred soft bridge session, the service MUST evaluate other eligible accounts/sessions before returning local overload. Successful reroutes MUST emit internal diagnostics such as `internal_soft_affinity_reroute`, without adding those names to the stable failure taxonomy.

#### Scenario: Response-create gate pressure evaluates soft alternatives

- **WHEN** response-create gate pressure saturates a preferred soft bridge session
- **THEN** the service evaluates other eligible accounts/sessions before returning local overload
- **AND** a successful reroute emits an internal diagnostic outside the stable failure taxonomy

### Requirement: Hard continuity remains owner-bound and bounded

Requests requiring `previous_response_id`, hard turn-state, account-scoped `input_file.file_id` pins, or other owner continuity MUST NOT silently reroute to an account that cannot preserve continuity. If the owner account/session is unavailable or saturated, the service MUST fail closed with an explicit retryable continuity/local overload reason, not flood the owner queue indefinitely.

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

### Requirement: Previous-response references remain hard owner continuity

A `previous_response_id` is a stored-object continuation reference and MUST remain owner-bound even when the request also carries `prompt_cache_key` or another soft locality key.

#### Scenario: Soft locality cannot replace a continuation owner

- **WHEN** a request carries both `previous_response_id` and a soft locality key
- **THEN** the stored-object continuation remains bound to its owner

### Requirement: WebSocket continuity state rows are pruned proactively
The existing leader-elected background cleanup loop SHALL prune persisted WebSocket continuity state rows older than 48 hours. Pruning SHALL be guarded so failures, including a missing `websocket_continuity_states` table mid-rollout, do not prevent other cleanup steps.

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

On a movable websocket request's retryable open-handshake timeout (`websocket_open_timeout` with same-contract retryable classification), the proxy MUST exclude the failed account for that request and invoke the existing failover ladder without retrying it first. Exclusion MUST NOT delete or rebind the durable sticky mapping. File-owner or previous-response-pinned requests MUST NOT cross accounts.

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

### Requirement: Open-timeout failover retains decision log fields

The open-timeout failover decision log line MUST record action `failover_next` alongside the existing request id, transport, account id, attempt, and failure class fields.

#### Scenario: Open-timeout failover records its decision context

- **WHEN** a retryable websocket open timeout invokes failover
- **THEN** the decision log records `failover_next`, request id, transport, account id, attempt, and failure class

### Requirement: Per-request account exclusion preserves sticky mappings

For every sticky kind, if a pinned account is absent from the candidate pool solely due to current-request exclusion (e.g. transport failover after a connect failure), selection MUST use a fallback for that request without deleting or rewriting the mapping. Mappings SHALL only be deleted or rebound for pool-membership changes (account removed or out of scope), permanent account status, budget-pressure reallocation, TTL expiry, or explicit administrative action.

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

Every selection carrying a sticky key MUST record `codex_lb_sticky_selection_total`, labeled by sticky kind and outcome. Outcomes MUST distinguish at least pinned account selected (`hit`), fallback without mapping mutation (`fallback`), fallback persisted over an existing mapping (`rebind`), and first placement (`new`). The metric MUST be a no-op when the metrics backend is unavailable.

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

### Requirement: Owner forwarding rejects illegal reconstructed header metadata

Owner-forwarded HTTP bridge requests MUST validate reconstructed bridge metadata before signing or posting headers to another owner. Unsafe original affinity, downstream turn-state, client-IP, origin or target instance, or reservation metadata MUST fail closed with structured `bridge_forward_invalid`, without dispatching the owner request.

#### Scenario: Unsafe reservation metadata fails closed

- **GIVEN** an owner-forward request carries API-key reservation metadata
- **AND** one reservation field contains an illegal HTTP header control character
- **WHEN** the origin builds the owner-forward request
- **THEN** it returns `bridge_forward_invalid`
- **AND** it does not post to the owner or silently omit only the reservation metadata

#### Scenario: Unsafe client header is omitted

- **GIVEN** an owner-forward request includes ordinary client headers with unsafe names or values
- **WHEN** the origin builds the owner-forward request
- **THEN** those client headers are not forwarded
- **AND** safe header values containing horizontal tab remain forwardable
- **AND** the signed bridge-forward metadata remains valid

### Requirement: Owner-forwarded headers exclude illegal controls without changing affinity

Signed bridge-header values MUST NOT contain controls below U+0020 except horizontal tab, or U+007F. Header names MUST NOT contain any such control, including horizontal tab. Ordinary client headers with unsafe names or values MUST be omitted from the forwarded header map. File-affinity and continuity-owner selection MUST remain unchanged.

#### Scenario: Horizontal tab is valid only in header values

- **GIVEN** a header value or name contains horizontal tab but no other control characters
- **WHEN** owner forwarding evaluates that header
- **THEN** the value remains forwardable but the name is unsafe
- **AND** file-affinity and continuity-owner selection remain unchanged

### Requirement: Canonical prompt-cache bridges preserve hard replica continuity

If durable lookup resolves incoming turn-state or a previous-response reference to a live bridge canonically keyed by `prompt_cache`, the origin MUST treat the request as hard bridge continuity for replica-owner routing. For another reachable live owner replica, it MUST use authenticated internal owner-forward transport and MUST NOT attempt soft local prompt-cache rebind.

#### Scenario: Turn-state continuation forwards to the canonical prompt-cache owner

- **GIVEN** a turn-state alias resolves to a live bridge canonically keyed by prompt cache on replica A
- **WHEN** the continuation arrives on replica B
- **THEN** replica B forwards the request internally to replica A
- **AND** it does not attempt to claim the canonical bridge locally
- **AND** replica B leaves no local inflight creation reservation for the forwarded bridge key

#### Scenario: Previous-response continuation forwards to the canonical prompt-cache owner

- **GIVEN** a previous-response reference resolves to a live bridge canonically keyed by prompt cache on replica A
- **WHEN** the continuation arrives on replica B
- **THEN** replica B forwards the request internally to replica A
- **AND** the client does not receive `bridge_instance_mismatch`

#### Scenario: Prompt-cache-only locality remains soft

- **GIVEN** a request has prompt-cache locality but no turn-state, previous-response, file pin, or other hard continuity evidence
- **WHEN** its locality owner is another replica
- **THEN** the receiving replica may use the existing soft local-rebind path

### Requirement: Canonical bridge keys do not weaken independent continuity constraints

Preserving the canonical prompt-cache key MUST NOT weaken hard continuation evidence or expose `bridge_instance_mismatch` for ordinary cross-replica continuation. File ownership MUST remain an independent account-affinity constraint, neither inferred from nor replaced by replica continuity ownership.

#### Scenario: Replica continuity does not establish file ownership

- **WHEN** a request resolves replica continuity for a canonical prompt-cache bridge
- **THEN** file ownership remains an independent account-affinity constraint
- **AND** replica continuity neither establishes nor replaces that constraint

### Requirement: Canonical prompt-cache locality and recovery retain bounded local rebinding

A request with only prompt-cache locality and no hard continuation evidence MUST retain existing soft local rebind behavior. Explicit recovery paths that have already established owner forwarding is unavailable MAY retain their bounded local-rebind behavior.

#### Scenario: Established forwarding unavailability permits bounded recovery

- **WHEN** an explicit recovery path has already established that owner forwarding is unavailable
- **THEN** it may retain its bounded local-rebind behavior
