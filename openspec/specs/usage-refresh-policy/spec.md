# usage-refresh-policy Specification

## Purpose
Define how background usage refresh reacts to auth-like failures without permanently hammering bad accounts.
## Requirements
### Requirement: Usage refresh cools down repeated auth-like failures

Background usage refresh MUST cool down accounts with repeated ambiguous `401` or `403` refresh failures. It MUST skip them until the cooldown expires or a later successful refresh clears it.

#### Scenario: Ambiguous usage 401 enters cooldown
- **WHEN** usage refresh receives a `401` that does not match a permanent deactivation signal
- **THEN** the account is not deactivated immediately
- **AND** subsequent refresh cycles skip the account until the cooldown window expires

#### Scenario: Successful refresh clears cooldown
- **WHEN** a later usage refresh succeeds for an account that had been cooled down
- **THEN** the cooldown is cleared
- **AND** normal refresh cadence resumes

### Requirement: Usage refresh deactivates on clear deactivation signals

Usage refresh MUST change an account to `deactivated` or `reauth_required` only for an explicit, account-specific upstream terminal signal. Recognized permanent-failure codes MUST use the existing permanent-failure account-status policy. An error message explicitly saying the account is deactivated MUST mark it `deactivated`.

#### Scenario: Bare usage 404 preserves account status

- **GIVEN** an account eligible for background usage refresh
- **WHEN** the usage endpoint returns HTTP `404` without an explicit permanent-failure code or deactivation message
- **THEN** the account's current status is unchanged
- **AND** the account is not marked routing-unavailable
- **AND** the response is recorded as a refresh failure and a later refresh cycle may retry it

#### Scenario: Bare usage 402 preserves account status

- **GIVEN** an account eligible for background usage refresh
- **WHEN** the usage endpoint returns HTTP `402` without an explicit permanent-failure code or deactivation message
- **THEN** the account's current status is unchanged
- **AND** the account is not marked routing-unavailable
- **AND** the response is recorded as a refresh failure and a later refresh cycle may retry it

#### Scenario: Usage 401 app session terminated requires re-authentication

- **WHEN** usage refresh receives HTTP `401`
- **AND** the upstream error code is `app_session_terminated`
- **THEN** the account is marked `reauth_required`
- **AND** later usage refresh cycles skip that account until re-authentication

#### Scenario: Explicit usage deactivation message deactivates account

- **WHEN** usage refresh receives an error whose message says `your OpenAI account has been deactivated`
- **AND** the error has no recognized permanent-failure code
- **THEN** the account is marked `deactivated`
- **AND** the account is marked routing-unavailable

### Requirement: Bare usage HTTP failures preserve account availability

A bare usage HTTP status, including `402` or `404`, MUST NOT change account status or routing availability. It MUST remain a refresh failure for existing logging, error accounting, and later refresh retries.

#### Scenario: Bare usage error retains retry accounting

- **WHEN** usage refresh receives a bare HTTP error without an explicit account-specific terminal signal
- **THEN** account status and routing availability remain unchanged
- **AND** existing refresh-failure logging, error accounting, and later retries still apply

### Requirement: token_expired at the refresh boundary deactivates the account

An OAuth refresh endpoint failure with `token_expired` MUST be treated as a permanent authentication failure, like `refresh_token_expired`, `refresh_token_reused`, or `refresh_token_invalidated`. The account MUST be deactivated and removed from the routing pool until re-authenticated.

#### Scenario: Refresh-time `token_expired` is classified as permanent

- **WHEN** `classify_refresh_error("token_expired")` is evaluated
- **THEN** it returns `True`

#### Scenario: Refresh-time `token_expired` deactivates the account

- **WHEN** `AuthManager.refresh_account` receives a `RefreshError("token_expired", ..., is_permanent=True)` from `refresh_access_token`
- **THEN** the account is transitioned to `DEACTIVATED`
- **AND** the deactivation reason references the re-login requirement so the dashboard can surface it
- **AND** the account is no longer selected by the load balancer until it is re-authenticated

#### Scenario: Usage-refresh-time `token_expired` deactivates the account

- **WHEN** background usage refresh observes an upstream error whose code is `token_expired` (via `_should_deactivate_for_usage_error`'s permanent-code check)
- **THEN** the account is transitioned to `DEACTIVATED` immediately, without entering the ambiguous-401 cooldown loop

### Requirement: Usage capacity recognizes upstream ChatGPT plan types

Absolute usage capacity MUST recognize account plan types from upstream ChatGPT auth and usage payloads. `prolite` MUST be supported with Plus x5 capacity (`1125.0` primary, `37800.0` secondary), preserving the stored plan type for display and request-log context.

#### Scenario: Pro Lite account contributes aggregate remaining credits

- **GIVEN** an active account whose stored `plan_type` is `prolite`
- **AND** its latest primary and secondary usage rows report `used_percent` below 100
- **WHEN** the system builds usage window summaries or per-account remaining credit values
- **THEN** the account contributes `1125.0` primary capacity and `37800.0` secondary capacity
- **AND** the computed remaining credits are non-zero according to the reported usage percent

### Requirement: Pro Lite accounts are eligible for Pro-gated models

Model registry plan eligibility MUST treat stored `prolite` plans as Pro-equivalent, preserving `prolite` for display and request-log context.

#### Scenario: Pro Lite account can be selected for a Pro-gated model

- **GIVEN** an active account whose stored `plan_type` is `prolite`
- **AND** its latest primary and secondary usage rows are below the configured usage threshold
- **AND** the requested model is allowed for `pro` accounts by the model registry
- **WHEN** proxy account selection evaluates eligible accounts for the requested model
- **THEN** the Pro Lite account remains eligible for selection
- **AND** the selection does not fail with `no_accounts`

### Requirement: Background usage refresh reconciles recoverable blocked statuses
Background usage refresh SHALL restore persisted `rate_limited` and `quota_exceeded` accounts to `active` after writing fresh usage snapshots that prove the blocked window recovered. Reconciliation SHALL be recovery-only and SHALL NOT move `active` accounts into blocked statuses.

#### Scenario: Scheduler recovers a stale rate-limited account from fresh primary usage
- **WHEN** an account is persisted as `rate_limited`
- **AND** the persisted rate-limit reset deadline has already elapsed
- **AND** a later background usage refresh writes a fresh primary usage row recorded after the persisted block marker
- **AND** that primary usage row reports usage below `100%`
- **THEN** the scheduler marks the account `active`
- **AND** it clears persisted `reset_at` and `blocked_at`

#### Scenario: Scheduler recovers a legacy rate-limited account without a block marker
- **WHEN** an account is persisted as `rate_limited`
- **AND** the persisted rate-limit reset deadline has already elapsed
- **AND** the account has no persisted block marker
- **AND** a later background usage refresh writes a recent primary usage row that reports usage below `100%`
- **THEN** the scheduler marks the account `active`
- **AND** it clears persisted `reset_at`

#### Scenario: Scheduler preserves legacy rate-limited accounts without recent primary usage
- **WHEN** an account is persisted as `rate_limited`
- **AND** the persisted rate-limit reset deadline has already elapsed
- **AND** the account has no persisted block marker
- **AND** the latest primary usage row is not recent enough to prove background refresh recovery
- **THEN** the scheduler leaves the account `rate_limited`

#### Scenario: Scheduler preserves an unexpired rate-limit cooldown
- **WHEN** an account is persisted as `rate_limited`
- **AND** its persisted rate-limit reset deadline is still in the future
- **AND** a later background usage refresh writes a fresh primary usage row recorded after the persisted block marker
- **AND** that primary usage row reports usage below `100%`
- **THEN** the scheduler leaves the account `rate_limited`

#### Scenario: Scheduler recovers a stale quota-exceeded account from fresh secondary usage
- **WHEN** an account is persisted as `quota_exceeded`
- **AND** a later background usage refresh writes a fresh secondary usage row that reports usage below `100%`
- **THEN** the scheduler marks the account `active`
- **AND** it clears persisted `reset_at` and `blocked_at`

#### Scenario: Scheduler does not tighten active accounts into blocked statuses
- **WHEN** background usage refresh evaluates an account currently persisted as `active`
- **THEN** the scheduler does not change that account to `rate_limited` or `quota_exceeded`

#### Scenario: Scheduler ignores stale pre-block recovery evidence
- **WHEN** an account is persisted as `rate_limited`
- **AND** the latest primary usage row was recorded before the persisted block marker
- **THEN** the scheduler leaves the account blocked

#### Scenario: Scheduler skips recovery when the account row changed concurrently
- **WHEN** background usage refresh determines that a blocked account is recoverable
- **AND** the persisted account status or reset markers change before the scheduler writes recovery
- **THEN** the scheduler skips the stale recovery write

#### Scenario: Scheduler clears stale deactivation reasons on recovery
- **WHEN** background usage refresh recovers a `rate_limited` or `quota_exceeded` account to `active`
- **THEN** the scheduler writes `deactivation_reason` as `NULL`

### Requirement: Usage refresh does not trust elapsed reset windows

Background usage refresh MUST treat a latest usage row with past `reset_at` as stale, even if its `recorded_at` is within the normal refresh interval.

#### Scenario: Past reset_at bypasses freshness

- **GIVEN** the latest usage row was recorded within the normal refresh interval
- **AND** that row's `reset_at` timestamp has already elapsed
- **WHEN** background usage refresh evaluates the account
- **THEN** the row is treated as stale
- **AND** codex-lb attempts a fresh upstream usage fetch

### Requirement: Blocked accounts refresh once their reset deadline elapses

For `RATE_LIMITED` or `QUOTA_EXCEEDED` accounts with elapsed persisted `reset_at`, background usage refresh MUST bypass normal freshness to permit recovery from upstream post-reset state. The bypass MUST NOT apply before that deadline.

#### Scenario: Quota-exceeded account with fresh primary row reaches reset deadline

- **GIVEN** an account is marked `QUOTA_EXCEEDED`
- **AND** the account's persisted `reset_at` timestamp has elapsed
- **AND** the latest primary usage row is still within the normal refresh interval
- **WHEN** background usage refresh evaluates the account
- **THEN** codex-lb performs an upstream usage fetch instead of waiting for the primary row to age out

#### Scenario: Rate-limited account reaches reset deadline

- **GIVEN** an account is marked `RATE_LIMITED`
- **AND** the account's persisted `reset_at` timestamp has elapsed
- **WHEN** background usage refresh evaluates the account
- **THEN** codex-lb performs an upstream usage fetch instead of waiting for the normal refresh interval

### Requirement: Credit-backed secondary quota remains usable

When deriving status from persisted usage snapshots, exhausted secondary-window usage alone MUST NOT mark an account `quota_exceeded` if the governing snapshot reports usable credit-backed capacity. Capacity is usable only if `credits_unlimited` is true or `credits_balance` is positive. `credits_has=true` with a missing, zero, or negative balance MUST NOT alone establish usable capacity.

#### Scenario: Secondary quota exhausted with credits remains active

- **GIVEN** an account is persisted as `quota_exceeded`
- **AND** its governing secondary-window usage reports `used_percent >= 100`
- **AND** the same usage snapshot reports usable credit-backed capacity
- **WHEN** proxy selection or account-summary mapping derives the effective status
- **THEN** the effective status is `active`

#### Scenario: Bare has-credits flag without spendable balance does not override secondary exhaustion

- **GIVEN** an account's governing secondary-window usage reports `used_percent >= 100`
- **AND** its primary-window usage reports `used_percent < 100`
- **AND** the same usage snapshot reports `credits_has = true`, `credits_unlimited` not true, and `credits_balance` missing, zero, or negative
- **WHEN** account-summary mapping derives the effective status with status inference from usage enabled
- **OR** proxy selection derives the effective status for an account persisted as `quota_exceeded` whose runtime reset deadline is still in the future
- **THEN** the effective status is `quota_exceeded`

#### Scenario: Exhausted primary window keeps rate-limit precedence

- **GIVEN** an account has usable credit-backed capacity in its usage snapshot
- **AND** its primary-window usage reports `used_percent >= 100`
- **WHEN** proxy selection or account-summary mapping derives the effective status
- **THEN** the effective status is `rate_limited`

#### Scenario: Operator-disabled states are preserved

- **GIVEN** an account is `paused` or `deactivated`
- **AND** its usage snapshot reports usable credit-backed capacity
- **WHEN** proxy selection or account-summary mapping derives the effective status
- **THEN** the account remains `paused` or `deactivated`

### Requirement: Credit-aware status mapping preserves shared precedence and disabled states

Proxy selection and account/dashboard summary status mapping MUST share this credit-aware interpretation: an account selected as usable MUST NOT simultaneously appear as `quota_exceeded` in the operator summary. Exhausted primary usage MUST take precedence as `rate_limited`. Paused or deactivated accounts MUST NOT reactivate solely because a usage snapshot reports usable credits.

#### Scenario: Credit-backed routing and dashboard status agree

- **WHEN** proxy selection treats an account as usable through credit-backed capacity
- **THEN** account/dashboard summary mapping does not simultaneously display it as `quota_exceeded`

### Requirement: Reset-confirmed limit warm-up

Limit warm-up SHALL be optional and disabled by default. When enabled globally and for an account, background usage refresh MAY send one minimal upstream Responses request after confirming a selected quota window moved from an exhausted sample to a newly available reset window.

#### Scenario: Warm-up is skipped unless reset is confirmed
- **GIVEN** limit warm-up is enabled globally and for an account
- **AND** the account's previous usage sample for a selected window was exhausted
- **WHEN** background usage refresh records a newer sample for that window with `used_percent < 100` and a later `reset_at`
- **THEN** the system sends at most one warm-up request for that account/window/reset tuple

#### Scenario: Warm-up is opt-in and safe by default
- **GIVEN** background usage refresh is preparing to evaluate limit warm-up candidates
- **WHEN** global limit warm-up is disabled
- **OR** the account is not opted in
- **THEN** background usage refresh MUST NOT send warm-up traffic

#### Scenario: Warm-up uses fresh opt-in state after usage refresh
- **GIVEN** an account was loaded before a background usage refresh cycle
- **AND** the account's limit warm-up opt-in changes while the refresh cycle is running
- **WHEN** the scheduler evaluates warm-up candidates after writing usage samples
- **THEN** the scheduler MUST evaluate the latest persisted opt-in value rather than the stale in-session account object

#### Scenario: Warm-up respects unsafe account states
- **WHEN** an account is paused, deactivated, rate-limited, quota-exceeded, or in an auth-refresh failure path
- **THEN** limit warm-up MUST NOT send traffic for that account

#### Scenario: Warm-up attempts are durable and deduplicated
- **WHEN** multiple refresh workers observe the same account/window/reset candidate
- **THEN** the database permits at most one persisted attempt for that tuple
- **AND** later refresh cycles skip that tuple after a prior attempt exists

#### Scenario: Staggered idle warm-up pre-starts rolling primary windows
- **GIVEN** limit warm-up and staggered idle warm-up are enabled globally
- **AND** multiple active accounts are opted into limit warm-up
- **AND** an opted-in account has a healthy idle primary 5h usage sample
- **WHEN** background usage refresh evaluates that account inside its deterministic stagger slot
- **THEN** the system MAY send one minimal upstream warm-up request for that account's current 300-minute cycle
- **AND** the system MUST NOT send another staggered idle warm-up for that same account/cycle tuple
- **AND** account slots MUST be spread deterministically across the 300-minute rolling window so restarts do not align all opted-in accounts into the same phase

#### Scenario: Staggered idle warm-up remains opt-in
- **GIVEN** limit warm-up is enabled globally and for an account
- **AND** staggered idle warm-up is disabled
- **WHEN** background usage refresh observes an idle primary 5h sample that is not a reset-confirmed transition
- **THEN** limit warm-up MUST NOT send synthetic traffic for that idle sample

### Requirement: Standard usage refresh snapshots persist atomically

For each successful account usage response, the system MUST persist every available normalized standard window (`primary`, `secondary`, applicable `monthly`) in one database transaction with one capture timestamp. Any standard-row persistence or commit failure MUST roll back the transaction so none of that response's standard rows is visible. A caller-owned database session MUST remain open and reusable after rollback.

#### Scenario: Multi-window response commits as one snapshot

- **WHEN** a successful account usage response contains multiple normalized standard windows
- **THEN** the system persists all of those standard rows in one transaction with one shared capture timestamp

#### Scenario: Later row failure leaves no partial snapshot

- **WHEN** persistence fails after at least one standard row from an account response has been staged
- **THEN** the system rolls back the transaction and no standard row from that response is visible

#### Scenario: Caller retains its session after rollback

- **WHEN** a caller-owned session is used for a standard usage snapshot and the snapshot transaction fails
- **THEN** the repository leaves that session open and reusable after rolling back the failed transaction

### Requirement: Standard snapshot atomicity preserves other usage persistence contracts

Atomic snapshot persistence applies to standard `usage_history` rows. Additional per-model usage history and independent live-ingest writes MUST retain their existing persistence contracts.

#### Scenario: Standard snapshot transactions do not redefine live ingestion

- **WHEN** an independent live-ingest write occurs
- **THEN** its existing persistence contract remains unchanged by standard snapshot atomicity

### Requirement: Background usage refresh is staggered across accounts

Background usage refresh MUST spread account refresh attempts across the configured interval, not refresh every eligible account in one burst. Each scheduler slice MUST attempt at most one eligible account. All eligible accounts SHOULD be considered once per full cycle.

#### Scenario: Scheduler refreshes one account per slice

- **GIVEN** two active accounts are eligible for usage refresh
- **WHEN** the scheduler runs consecutive refresh slices
- **THEN** the first slice attempts one account
- **AND** the second slice attempts the other account
- **AND** cache invalidation for usage-derived routing state runs at the cycle boundary

#### Scenario: Unrefreshable accounts are skipped by scheduler rotation

- **GIVEN** one account is active
- **AND** one account is deactivated
- **AND** one account requires re-authentication
- **WHEN** the scheduler builds the refresh rotation
- **THEN** only the active account is considered

#### Scenario: Selected slot scopes usage history and follow-up work

- **GIVEN** two eligible accounts have stored primary, secondary, and monthly usage
- **AND** the first account is selected for the current scheduler slice
- **WHEN** the scheduler reads before/after usage and evaluates warm-up and recoverable status
- **THEN** every usage-history lookup is filtered to the first account
- **AND** only the first account is passed to usage refresh, warm-up candidate evaluation, and recoverable-status evaluation
- **AND** the second account cannot be mutated or contacted during that slice

#### Scenario: Warm-up phase cohort does not widen evaluation scope

- **GIVEN** multiple warm-up-enabled accounts participate in staggered-idle phase calculation
- **AND** one account is selected for the current usage-refresh slice
- **WHEN** refreshed usage is evaluated for warm-up
- **THEN** the phase calculation retains the eligible fleet cohort
- **AND** only the selected account can create a warm-up attempt or send warm-up traffic

#### Scenario: Selected-account failure does not fail over within the slice

- **GIVEN** two accounts are eligible for scheduler rotation
- **AND** the first account is selected
- **WHEN** that account's usage refresh fails
- **THEN** the scheduler does not attempt the second account in the same slice
- **AND** the second account remains eligible for its normal later slice

#### Scenario: Scheduler session closes before selected-account network work

- **GIVEN** the scheduler loaded the account roster and selected account usage
- **WHEN** the selected account's upstream refresh starts
- **THEN** the scheduler read session is already closed
- **AND** any concurrent warm-up follow-up owns an independent database session

### Requirement: Refresh slices isolate selected-account work and failures

Each slice MUST select its account before reading usage history. Latest-usage lookups, updater input, warm-up candidate evaluation, and recoverable-status evaluation MUST be scoped to that account. A selected-account refresh failure MUST NOT trigger same-slice fallback to another account.

#### Scenario: Failed selected-account refresh does not widen evaluation scope

- **WHEN** the selected account's refresh fails
- **THEN** that slice does not fall back to another account
- **AND** its usage lookups and follow-up evaluations remain scoped to the selected account

### Requirement: Scheduler roster retention permits only rotation and warm-up phase calculation

The scheduler MAY retain the full eligible account roster only to choose deterministic rotation and calculate staggered warm-up phases. That roster MUST NOT cause usage-history reads, upstream refresh attempts, warm-up sends, or status mutations for an unrelated account in the slice.

#### Scenario: Retained roster does not trigger unrelated account work

- **WHEN** a slice retains the full eligible roster for rotation or warm-up phases
- **THEN** the roster causes no usage-history reads, refresh attempts, warm-up sends, or status mutations for unrelated accounts

### Requirement: Usage refresh releases scheduler sessions before network work

Database sessions used to load scheduler state MUST close before upstream network I/O begins. Concurrent follow-up work MUST NOT share an `AsyncSession`.

#### Scenario: Concurrent follow-up uses independent sessions

- **WHEN** usage-refresh follow-up tasks run concurrently
- **THEN** they do not share an `AsyncSession`

### Requirement: Force Probe upstream request omits unsupported output-token limit

Dashboard Force Probe (`POST /api/accounts/{account_id}/probe`) MUST omit `max_output_tokens` at every value from its direct upstream `responses.create`. It MUST NOT substitute another output-token cap, retry without the field, or send more than one upstream request per probe.

#### Scenario: Probe body carries no output-token limit

- **WHEN** an operator POSTs to `/api/accounts/{account_id}/probe` for an `active`, `rate_limited`, or `quota_exceeded` account
- **THEN** exactly one upstream `responses.create` is sent to `{upstream_base_url}/codex/responses`
- **AND** its JSON body has no `max_output_tokens` key (neither `1`, `16`, nor any other value)
- **AND** its JSON body carries the probe model, the one-dot `instructions` and `input`, `stream=true`, and `store=false`

#### Scenario: Upstream that rejects the field accepts the probe

- **GIVEN** an upstream that responds `400` to any `responses.create` body containing `max_output_tokens` and `200` otherwise
- **WHEN** an operator POSTs to `/api/accounts/{account_id}/probe` for a probeable account
- **THEN** the endpoint responds `200`
- **AND** the response body reports `probeStatusCode` `200`

#### Scenario: Upstream status still propagates verbatim

- **WHEN** the upstream answers the probe with any HTTP status, including a non-2xx status
- **THEN** `probe_status_code` equals that status
- **AND** no second upstream request is sent

#### Scenario: Network failure keeps the zero sentinel within timeout bounds

- **WHEN** the probe request raises a client error or exceeds `PROBE_REQUEST_TIMEOUT_SECONDS` total or `PROBE_CONNECT_TIMEOUT_SECONDS` socket connect
- **THEN** `probe_status_code` is `0`
- **AND** the decrypted access token is not logged

#### Scenario: Account headers and stream handling are preserved

- **WHEN** the probe is sent for an account whose stored `chatgpt_account_id` does not start with `email_` or `local_`
- **THEN** the request carries `Authorization: Bearer <decrypted access token>`, `Accept: text/event-stream`, and `chatgpt-account-id` set to that id
- **AND** the probe returns the status after response headers without reading the SSE body

### Requirement: Force Probe preserves its minimal request body

The probe body MUST contain the request's `model`, else `DEFAULT_PROBE_MODEL`, fixed one-dot `instructions` and `input`, `stream=true`, and `store=false`.

#### Scenario: Probe without a requested model uses the default

- **WHEN** a Force Probe request omits `model`
- **THEN** its upstream body uses `DEFAULT_PROBE_MODEL`, one-dot `instructions` and `input`, `stream=true`, and `store=false`

### Requirement: Force Probe preserves upstream target and account headers

The probe MUST target `{upstream_base_url}/codex/responses`, inserting `/backend-api` when absent. It MUST carry `Authorization: Bearer <decrypted access token>` and `Accept: text/event-stream`. It MUST carry `chatgpt-account-id` unless the stored id is absent or starts with `email_` or `local_`.

#### Scenario: Synthetic account id is omitted from the probe

- **WHEN** the stored account id is absent or starts with `email_` or `local_`
- **THEN** the probe omits `chatgpt-account-id` but retains its authorization and SSE accept headers

### Requirement: Force Probe preserves bounded header-only status handling

The probe MUST respect `PROBE_REQUEST_TIMEOUT_SECONDS` total and `PROBE_CONNECT_TIMEOUT_SECONDS` socket-connect limits. It MUST return when response headers arrive without consuming the SSE body. `probe_status_code` MUST be the upstream HTTP status verbatim, or `0` on client or timeout error.

#### Scenario: Probe status does not depend on consuming the stream

- **WHEN** the probe receives upstream response headers
- **THEN** it returns that HTTP status without consuming the SSE body

### Requirement: Force Probe preserves surrounding dashboard operations

Force Probe MUST preserve post-probe forced usage refresh, before/after snapshot, audit entry, dashboard authentication, and existing `404`/`409` rejections.

#### Scenario: Probe retains authenticated audit and refresh behavior

- **WHEN** the dashboard performs Force Probe
- **THEN** its existing authentication, rejection, audit, snapshot, and forced usage-refresh behavior remains unchanged
