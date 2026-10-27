# api-keys Specification

## Purpose

Define API key lifecycle, enforcement, accounting, and dashboard management contracts for downstream clients.
## Requirements
### Requirement: API Key creation

The system SHALL support admin key creation via `POST /api/api-keys/`: required `name`, optional `allowed_models` (list), `weekly_token_limit` (integer), `expires_at` (ISO 8601 datetime), and `assigned_account_ids` (list).

It MUST generate `sk-clb-{48 hex chars}`, store only its `sha256` hash in the database, and return the plain key exactly once, on creation. It MUST accept timezone-aware ISO 8601 `expiresAt`, persist UTC-naive values, and return UTC expirations.

#### Scenario: Create key and show plain key

- **WHEN** admin submits `POST /api/api-keys/` with a valid payload
- **THEN** the response contains the full plain key exactly once and the system never returns the plain key on subsequent reads

#### Scenario: Create key with timezone-aware expiration

- **WHEN** admin submits `POST /api/api-keys/` with `{ "name": "dev-key", "expiresAt": "2025-12-31T00:00:00Z" }`
- **THEN** the system persists the expiration successfully without PostgreSQL datetime binding errors
- **AND** the response returns `expiresAt` representing the same UTC instant

### Requirement: API Key creation account assignments

On `POST /api/api-keys/`, missing or empty `assigned_account_ids` SHALL create an unscoped key applying to all accounts. One or more valid IDs SHALL enable assignment scope and persist assignments.

#### Scenario: Create unscoped key without assigned accounts

- **WHEN** admin submits `POST /api/api-keys/` without `assignedAccountIds`
- **THEN** the created key returns `accountAssignmentScopeEnabled = false`
- **AND** `assignedAccountIds = []`

#### Scenario: Create scoped key with assigned accounts

- **WHEN** admin submits `POST /api/api-keys/` with `assignedAccountIds` containing valid account IDs
- **THEN** the created key returns `accountAssignmentScopeEnabled = true`
- **AND** `assignedAccountIds` matches the supplied accounts

#### Scenario: Reject unknown assigned account IDs on create

- **WHEN** admin submits `POST /api/api-keys/` with an unknown account ID in `assignedAccountIds`
- **THEN** the system returns 400

### Requirement: API Key update
The system SHALL allow updating key properties via `PATCH /api/api-keys/{id}`. Updatable fields: `name`, `allowedModels`, `weeklyTokenLimit`, `expiresAt`, `isActive`. The key hash and prefix MUST NOT be modifiable. The system MUST accept timezone-aware ISO 8601 datetimes for `expiresAt` and normalize them to UTC naive before persistence.

#### Scenario: Update key with timezone-aware expiration
- **WHEN** admin submits `PATCH /api/api-keys/{id}` with `{ "expiresAt": "2025-12-31T00:00:00Z" }`
- **THEN** the system persists the expiration successfully without PostgreSQL datetime binding errors
- **AND** the response returns `expiresAt` representing the same UTC instant

#### Scenario: Update non-existent key

- **WHEN** admin submits `PATCH /api/api-keys/{id}` with an unknown ID
- **THEN** the system returns 404

### Requirement: API Key deletion

The system SHALL allow deleting an API key via `DELETE /api/api-keys/{id}`. Deletion MUST be permanent and the key MUST immediately stop authenticating.

#### Scenario: Delete existing key

- **WHEN** admin calls `DELETE /api/api-keys/{id}` for an existing key
- **THEN** the key is permanently removed from the database and returns 204

#### Scenario: Delete non-existent key

- **WHEN** admin calls `DELETE /api/api-keys/{id}` with an unknown ID
- **THEN** the system returns 404

### Requirement: API Key regeneration

The system SHALL allow regenerating an API key via `POST /api/api-keys/{id}/regenerate`. This MUST generate a new key value (new hash, new prefix) while preserving all other properties (name, models, limits, expiration). The new plain key MUST be returned exactly once.

#### Scenario: Regenerate key

- **WHEN** admin calls `POST /api/api-keys/{id}/regenerate`
- **THEN** the system returns the updated key object with a new `key` and `keyPrefix`; the old key immediately stops authenticating

### Requirement: API Key authentication global switch
`DashboardSettings` SHALL expose boolean `api_key_auth_enabled` (default false). When false, local protected proxy requests MAY omit API keys. Operators MAY allow specific non-local clients unauthenticated access via `proxy_unauthenticated_client_cidrs`. Other non-local requests MUST be rejected until proxy authentication is configured. When true, protected proxy routes require a valid API key via Bearer authentication in `Authorization`.

#### Scenario: Enable API key auth

- **WHEN** admin submits `PUT /api/settings` with `{ "apiKeyAuthEnabled": true }`
- **THEN** subsequent proxy requests without a valid Bearer token are rejected with 401

#### Scenario: Disable API key auth for a local request

- **WHEN** admin submits `PUT /api/settings` with `{ "apiKeyAuthEnabled": false }`
- **AND** a local client calls a protected proxy route
- **THEN** the request is allowed without API key authentication

#### Scenario: Disable API key auth for a non-local request

- **WHEN** admin submits `PUT /api/settings` with `{ "apiKeyAuthEnabled": false }`
- **AND** a non-local client calls a protected proxy route
- **THEN** the request is rejected with 401 until proxy authentication is configured

#### Scenario: Disable API key auth for an explicitly allowlisted proxy client
- **WHEN** admin submits `PUT /api/settings` with `{ "apiKeyAuthEnabled": false }`
- **AND** the request socket peer IP belongs to configured `proxy_unauthenticated_client_cidrs`
- **THEN** the protected proxy route proceeds without API key authentication

#### Scenario: Disable API key auth for a non-local request outside the explicit allowlist
- **WHEN** admin submits `PUT /api/settings` with `{ "apiKeyAuthEnabled": false }`
- **AND** a non-local client calls a protected proxy route
- **AND** the request socket peer IP is outside configured `proxy_unauthenticated_client_cidrs`
- **THEN** the request is rejected with 401 until proxy authentication is configured

#### Scenario: Enable without any keys created

- **WHEN** admin enables API key auth but no keys exist
- **THEN** all proxy requests are rejected with 401 (the system SHALL NOT prevent enabling even if no keys exist)

#### Scenario: Toggle API key auth

- **WHEN** admin toggles `apiKeyAuthEnabled` in settings
- **THEN** the system calls `PUT /api/settings` and reflects the new state

### Requirement: API Key Bearer authentication guard
With `api_key_auth_enabled=true`, API keys SHALL be validated on `/v1/*`, `/backend-api/codex/*`, and `/backend-api/transcribe`, excluding `/api/codex/usage`. A router-level `Security` dependency, not ASGI middleware, MUST hash the Bearer token with `sha256` and look it up in `api_keys`. It SHALL return typed `ApiKeyData` directly to handlers. Handlers MUST NOT use `request.state` for key data. Failures SHALL raise domain exceptions, formatted by handlers in the OpenAI error envelope.

#### Scenario: Disabled auth allowlist uses raw socket peer only
- **WHEN** `api_key_auth_enabled` is false
- **AND** forwarded headers claim a different client IP
- **AND** the request socket peer IP is outside configured `proxy_unauthenticated_client_cidrs`
- **THEN** the dependency rejects the request with 401
- **AND** forwarded headers do not satisfy the explicit allowlist

#### Scenario: API key guard route scope

- **WHEN** `api_key_auth_enabled` is true and a request is made to `/v1/responses`, `/backend-api/codex/responses`, `/v1/audio/transcriptions`, or `/backend-api/transcribe`
- **THEN** the API key guard validation is applied

#### Scenario: Codex usage excluded from API key guard scope

- **WHEN** `api_key_auth_enabled` is true and a request is made to `/api/codex/usage`
- **THEN** API key guard validation is not applied

#### Scenario: Valid API key injected into handler

- **WHEN** `api_key_auth_enabled` is true and a valid Bearer token is provided
- **THEN** the route handler receives a typed `ApiKeyData` parameter (not `request.state`)

#### Scenario: API key auth disabled returns None for local requests

- **WHEN** `api_key_auth_enabled` is false
- **AND** the request is classified as local
- **THEN** the dependency returns `None` and the request proceeds without authentication

#### Scenario: API key auth disabled rejects non-local requests

- **WHEN** `api_key_auth_enabled` is false
- **AND** the request is classified as non-local
- **AND** the request socket peer IP is outside configured `proxy_unauthenticated_client_cidrs`
- **THEN** the dependency rejects the request with 401

### Requirement: Model restriction enforcement

The proxy service layer, not middleware, SHALL enforce per-key model restrictions. Requests outside non-null, non-empty `allowed_models` MUST be rejected. `/v1/models` MUST filter by the authenticated key's `allowed_models`. Fixed-model endpoints such as `/v1/audio/transcriptions` and `/backend-api/transcribe` MUST check effective model `gpt-4o-transcribe`.

#### Scenario: Requested model not allowed

- **WHEN** a key has `allowed_models: ["o3-pro"]` and a request is made for model `gpt-4.1`
- **THEN** the proxy returns 403 with OpenAI-format error `{ "error": { "code": "model_not_allowed", "message": "This API key does not have access to model 'gpt-4.1'" } }`

#### Scenario: Cursor alias allowed model permits canonical request

- **WHEN** a key has `allowed_models: ["gpt-5.4-mini-high"]`
- **AND** a request is made for model `gpt-5.4-mini`
- **THEN** the proxy permits the request because the allowed alias resolves to the requested canonical model

#### Scenario: All models allowed

- **WHEN** a key has `allowed_models: null`
- **THEN** any model is permitted

#### Scenario: Model list filtered

- **WHEN** a key with `allowed_models: ["o3-pro"]` calls `GET /v1/models`
- **THEN** the response contains only models matching the allowed list

#### Scenario: Model list canonicalizes Cursor aliases

- **WHEN** a key with `allowed_models: ["gpt-5.4-mini-high"]` and `enforced_model: "gpt-5.4-mini-high"` calls `GET /v1/models`
- **THEN** the response contains the canonical model `gpt-5.4-mini`
- **AND** the response does not expose a synthetic `gpt-5.4-mini-high` model id

#### Scenario: Codex model list visibility canonicalizes Cursor aliases

- **WHEN** a key with `allowed_models: ["gpt-5.4-mini-high"]`, `enforced_model: "gpt-5.4-mini-high"`, and `apply_to_codex_model=true` calls `GET /backend-api/codex/models`
- **THEN** the canonical `gpt-5.4-mini` entry is visible with `visibility: "list"`
- **AND** other entries are hidden according to the API key allowlist policy

#### Scenario: No API key auth (disabled)

- **WHEN** `api_key_auth_enabled` is false and a request is made to `/v1/models`
- **THEN** the full model catalog is returned

#### Scenario: Fixed transcription model not allowed

- **WHEN** a key has `allowed_models: ["gpt-5.1"]` and a request is made to `/v1/audio/transcriptions` or `/backend-api/transcribe`
- **THEN** the proxy returns 403 with OpenAI-format error code `model_not_allowed` for model `gpt-4o-transcribe`

### Requirement: API key Codex catalog visibility policy

`/backend-api/codex/models` SHALL retain default allowlist filtering. For an authenticated key with `apply_to_codex_model = true` and non-empty `allowed_models`, it SHALL instead return the full catalog with `visibility: "list"` for allowlisted entries and `visibility: "hide"` for all others. With null or empty `allowed_models`, it SHALL preserve original behavior even when opted in, as no allowlist applies.

#### Scenario: Codex models keep filtered behavior by default
- **WHEN** a key has `allowed_models: ["o3-pro"]` and `apply_to_codex_model: false`
- **AND** the key calls `GET /backend-api/codex/models`
- **THEN** the response contains only models matching the allowed list

#### Scenario: Codex models rewrite visibility when opted in
- **WHEN** a key has `allowed_models: ["o3-pro"]` and `apply_to_codex_model: true`
- **AND** the key calls `GET /backend-api/codex/models`
- **THEN** the response contains the full catalog
- **AND** the `o3-pro` entry has `visibility: "list"`
- **AND** every model not in `allowed_models` has `visibility: "hide"`

#### Scenario: Codex models preserve original behavior without an allowlist
- **WHEN** a key has `allowed_models: null` and `apply_to_codex_model: true`
- **AND** the key calls `GET /backend-api/codex/models`
- **THEN** the response preserves the original `/backend-api/codex/models` behavior because there is no allowlist to apply
### Requirement: Weekly token usage tracking

The system SHALL atomically increment `weekly_tokens_used` on the API key record when a proxy request completes with token usage data. The token count MUST be `input_tokens + output_tokens`. If token usage is unavailable (error response), the counter MUST NOT be incremented.

#### Scenario: Successful request with usage

- **WHEN** a proxy request completes with `input_tokens: 100, output_tokens: 50` for an authenticated key
- **THEN** `weekly_tokens_used` is atomically incremented by 150

#### Scenario: Request with no usage data

- **WHEN** a proxy request fails with an error and no usage data is returned
- **THEN** `weekly_tokens_used` is not incremented

#### Scenario: Request without API key auth

- **WHEN** `api_key_auth_enabled` is false and a proxy request completes
- **THEN** no API key usage tracking occurs

### Requirement: Weekly token usage reset

The system SHALL retain lazy on-read resets for API key usage limits. On key validation, a limit with `reset_at < now()` MUST have its counter reset and `reset_at` advanced by whole window intervals into the future. An hourly background fallback sweep MUST also repair expired usage without validation requests.

#### Scenario: Weekly reset triggered on validation

- **WHEN** an API key is validated and `weekly_reset_at` is 2 weeks in the past
- **THEN** `weekly_tokens_used` is set to 0 and `weekly_reset_at` is advanced by 14 days (2 × 7 days) to a future date

#### Scenario: No reset needed

- **WHEN** an API key is validated and `weekly_reset_at` is in the future
- **THEN** no reset occurs; `weekly_tokens_used` retains its current value

#### Scenario: Hourly fallback resets expired usage without a read

- **WHEN** an API key usage limit is expired and no validation request occurs
- **THEN** the hourly background fallback resets `current_value` to 0 and advances `reset_at` into the future

### Requirement: RequestLog API key reference

The system SHALL record the `api_key_id` in the `request_logs` table for proxy requests authenticated with an API key. The field MUST be NULL when API key auth is disabled or the request is unauthenticated.

#### Scenario: Authenticated request logged

- **WHEN** a proxy request is authenticated with API key `key-123` and completes
- **THEN** the `request_logs` entry has `api_key_id = "key-123"`

#### Scenario: Unauthenticated request logged

- **WHEN** API key auth is disabled and a proxy request completes
- **THEN** the `request_logs` entry has `api_key_id = NULL`

### Requirement: Frontend API Key management

SPA settings SHALL include API Key management: an `apiKeyAuthEnabled` toggle, a prefix/name/models/limit/usage/expiry/status table, a create dialog (name, model/assigned-account selection, weekly limit, expiry date), and edit/delete/regenerate actions. Creation MUST show a plain-key dialog warning it will not be shown again, copyable in secure and non-secure contexts.

#### Scenario: Create key with optional account scoping

- **WHEN** an admin opens the create API key dialog
- **THEN** the dialog shows the Assigned accounts picker
- **AND** leaving the picker at `All accounts` creates an unscoped key
- **AND** selecting one or more accounts creates a scoped key for only those accounts

#### Scenario: Create key and show plain key

- **WHEN** admin creates a key via the UI
- **THEN** a dialog shows the full plain key with a copy button and a warning message

#### Scenario: API key dialog copy fallback

- **WHEN** a user clicks Copy for the created API key inside the dialog
- **THEN** the copy operation succeeds using secure Clipboard API when available
- **AND** falls back to dialog-scoped `execCommand("copy")` when secure Clipboard API is unavailable

### Requirement: API key dialogs manage Codex model visibility

Create/edit API key dialogs SHALL put an `Apply to codex /model` checkbox directly below `Allowed models`. It SHALL default unchecked for new keys and edit existing keys' stored value.

#### Scenario: Create key with codex model visibility option
- **WHEN** an admin opens the create API key dialog
- **THEN** the `Apply to codex /model` checkbox appears directly below `Allowed models`
- **AND** it is unchecked by default

#### Scenario: Edit key with stored codex model visibility option
- **WHEN** an admin opens the edit API key dialog for a key with `apply_to_codex_model: true`
- **THEN** the `Apply to codex /model` checkbox is shown as checked
### Requirement: Cost accounting uses model and service-tier pricing
API key `cost_usd` MUST use resolved model pricing and the upstream response's authoritative `service_tier`, falling back to the forwarded request tier only if omitted. Non-standard tiers MUST use published pricing for the tier actually used, not standard-tier pricing.

#### Scenario: Priority-tier request increments cost limit
- **WHEN** an authenticated request for a priced model is finalized with `service_tier: "priority"`
- **THEN** the system computes `cost_usd` using the priority-tier rate for that model

#### Scenario: Flex-tier request increments cost limit
- **WHEN** an authenticated request for a priced model is finalized with `service_tier: "flex"`
- **THEN** the system computes `cost_usd` using the flex-tier rate for that model

#### Scenario: Standard-tier request keeps standard pricing
- **WHEN** an authenticated request for the same model is finalized without `service_tier`
- **THEN** the system computes `cost_usd` using the standard-tier rate

### Requirement: gpt-5.4 pricing is recognized
The system MUST recognize `gpt-5.4` pricing when computing request costs. For standard-tier requests with more than 272K input tokens, the system MUST apply the published higher long-context rates.

#### Scenario: gpt-5.4 request priced at standard tier
- **WHEN** a request for `gpt-5.4` completes with standard service tier
- **THEN** the system computes non-zero cost using the configured `gpt-5.4` standard rates

#### Scenario: gpt-5.4 long-context request priced at long-context rates
- **WHEN** a standard-tier `gpt-5.4` request completes with more than 272K input tokens
- **THEN** the system computes cost using the configured long-context `gpt-5.4` rates

### Requirement: Model-scoped limit enforcement

Authentication and quota enforcement SHALL be separate. Auth-guard `validate_key()` SHALL check only existence, active status, expiry, basic reset. Quotas SHALL be enforced when the model is known: limits apply iff `model_filter is None` or equals `request_model`. Model-less requests (e.g., `/v1/models`) SHALL evaluate only global limits. The typed service contract SHALL be `enforce_limits_for_request(key_id: str, *, request_model: str | None, request_service_tier: str | None = None) -> None`.

#### Scenario: Model-scoped limit does not block other models

- **WHEN** `model_filter="gpt-5.1"` limit is exhausted
- **AND** request model is `gpt-4o-mini`
- **THEN** the request is allowed

#### Scenario: Model-scoped limit blocks matching model

- **WHEN** `model_filter="gpt-5.1"` limit is exhausted
- **AND** request model is `gpt-5.1`
- **THEN** the request returns 429

#### Scenario: Model-scoped limit does not block model-less endpoints

- **WHEN** `model_filter="gpt-5.1"` limit is exhausted
- **AND** request is to `/v1/models` (no model context)
- **THEN** the request is allowed

#### Scenario: Global limit blocks all proxy requests

- **WHEN** a global limit (no `model_filter`) is exhausted
- **THEN** all proxy requests return 429

### Requirement: Limit update with usage state preservation

Limit updates SHALL match rules by `(limit_type, limit_window, model_filter)`:
- Matches SHALL preserve `current_value` and `reset_at`, updating only `max_value`.
- New rules use a fresh `reset_at`. With `resetUsage=false`, initialize `current_value` from successful request-log usage in its current window. With `resetUsage=true`, set it to 0.
- Delete removed rules.

Usage SHALL reset only through an explicit action (`reset_usage` field or dedicated endpoint), never metadata or policy edits.

#### Scenario: Metadata-only edit preserves usage state

- **WHEN** an API key PATCH updates only name or is_active
- **AND** `limits` field is not included in the payload
- **THEN** existing `current_value` and `reset_at` are unchanged

#### Scenario: Same policy re-submission preserves usage state

- **WHEN** an API key PATCH includes `limits` with identical rules (same type/window/filter/max_value)
- **THEN** existing `current_value` and `reset_at` are unchanged

#### Scenario: max_value adjustment preserves counters

- **WHEN** an API key PATCH includes `limits` with a changed `max_value` for an existing rule
- **THEN** `current_value` and `reset_at` are preserved; only the threshold changes

#### Scenario: Explicit reset action resets usage

- **WHEN** an explicit usage reset action is invoked
- **THEN** `current_value` is set to 0 and `reset_at` is refreshed

### Requirement: API key edit payload — conditional limits transmission

The frontend edit dialog SHALL normalize and compare initial/current limit values and send PATCH `limits` only when values change. Metadata-only edits (name, is_active) MUST omit `limits`. Reordered identical rules MUST count as unchanged and omit `limits`.

Backend: absent `limits` leaves policy and usage/reset state unchanged. Present `limits` replaces policy with a state-preserving upsert.

#### Scenario: Name-only edit omits limits from payload

- **WHEN** only the API key name is modified in the edit dialog
- **THEN** the PATCH payload does not include the `limits` field

#### Scenario: Reordered identical rules treated as unchanged

- **WHEN** the same limit rules are submitted in a different order
- **THEN** the system treats this as unchanged and omits `limits` from the payload

### Requirement: Public OpenAI-compatible model list filtering

`/api/models`, `/v1/models`, and `/backend-api/codex/models.data` SHALL share one predicate: `model.supported_in_api` is true and, if `allowed_models` is configured, the model is in that set. The Codex-native `/backend-api/codex/models.models` catalog SHALL expose unsupported upstream models only for Codex shell-command models (`shell_type="shell_command"`). Unsupported non-shell models SHALL stay hidden.

#### Scenario: Unsupported model excluded from /v1/models

- **WHEN** a model snapshot contains a model with `supported_in_api=false`
- **THEN** that model is not included in the `/v1/models` response

#### Scenario: Unsupported non-shell model excluded from /backend-api/codex/models

- **WHEN** a model snapshot contains a model with `supported_in_api=false`
- **AND** the model is not a Codex shell-command model
- **THEN** that model is not included in the `/backend-api/codex/models` response

#### Scenario: Unsupported Codex shell model included only in Codex-native catalog

- **WHEN** a model snapshot contains a model with `supported_in_api=false`
- **AND** the model has `shell_type="shell_command"`
- **THEN** that model is included in `/backend-api/codex/models.models`
- **AND** that model is not included in `/backend-api/codex/models.data`
- **AND** that model is not included in `/api/models` or `/v1/models`

#### Scenario: Allowed but unsupported model excluded

- **WHEN** a model is in the `allowed_models` set but has `supported_in_api=false`
- **AND** the model is not a Codex shell-command model
- **THEN** that model is not exposed in any model list endpoint

#### Scenario: gpt-5.3-codex aliases share availability gate consistently

- **WHEN** `gpt-5.3-codex` has `supported_in_api=false`
- **AND** `gpt-5.3-codex-spark` has `supported_in_api=true`
- **THEN** `/api/models`, `/v1/models`, and `/backend-api/codex/models.data`
      expose `gpt-5.3-codex-spark` but do not expose `gpt-5.3-codex`

#### Scenario: Consistent model set across endpoints

- **GIVEN** any model registry state
- **THEN** `/api/models`, `/v1/models`, and `/backend-api/codex/models.data` expose the same OpenAI-compatible set of models

### Requirement: Reservation 정산 exactly-once 보장

Usage reservation의 최종 정산(finalize 또는 release)은 요청 단위에서 정확히 1회 수행되어야 한다. 재시도 가능한 중간 attempt에서는 정산을 defer하고, 요청 종료 시점에서 단일 지점이 정산 책임을 갖는다. 시스템은 이 동작을 SHALL 보장해야 한다.

#### Scenario: 스트림 401 → refresh retry 성공 시 finalize 1회

- **WHEN** 첫 `_stream_once()` attempt에서 401을 수신하고 계정 refresh 후 재시도가 성공하면
- **THEN** 첫 attempt에서는 reservation 정산이 수행되지 않아야 한다 (SHALL)
- **AND** 최종 성공 시점에서 `finalize_usage_reservation()`이 정확히 1회 호출되어야 한다 (SHALL)
- **AND** 실제 token 사용량이 quota에 반영되어야 한다 (SHALL)

#### Scenario: 스트림 401 → retry 소진 실패 시 release 1회

- **WHEN** 401 후 재시도를 모두 소진하여 요청이 최종 실패하면
- **THEN** `release_usage_reservation()`이 정확히 1회 호출되어야 한다 (SHALL)
- **AND** 예약된 quota가 원복되어야 한다 (SHALL)

#### Scenario: 스트림 성공 시 finalize 1회

- **WHEN** `_stream_once()`가 retry 없이 첫 attempt에서 성공하면
- **THEN** `finalize_usage_reservation()`이 정확히 1회 호출되어야 한다 (SHALL)

### Requirement: 조기 종료 경로에서 reservation release 보장

Reservation 생성 후 upstream API 호출에 진입하지 않고 종료되는 모든 경로에서 reservation이 release되어야 한다. `reserved` 상태로 남는 reservation이 존재하면 안 된다. 시스템은 이 동작을 SHALL 보장해야 한다.

#### Scenario: no_accounts 즉시 종료 시 release

- **WHEN** reservation 생성 후 `_stream_with_retry()`가 사용 가능한 계정 없음(`no_accounts`)으로 즉시 종료되면
- **THEN** `release_usage_reservation()`이 호출되어 reservation이 `released` 상태로 전이되어야 한다 (SHALL)
- **AND** pre-reserved quota가 원복되어야 한다 (SHALL)

#### Scenario: 재시도 소진 후 no_accounts 종료 시 release

- **WHEN** 재시도 루프가 모든 attempt를 소진한 후 `no_accounts`로 종료되면
- **THEN** `release_usage_reservation()`이 호출되어야 한다 (SHALL)

#### Scenario: reservation 미생성 시 정산 스킵

- **WHEN** API key auth가 비활성이거나 reservation이 생성되지 않은 상태에서 요청이 종료되면
- **THEN** 정산 로직이 안전하게 스킵되어야 하며 에러가 발생하지 않아야 한다 (SHALL)

### Requirement: Compact 경로 예외 무관 reservation cleanup

`_compact_responses()` 경로에서 reservation이 존재할 때, 어떤 예외 타입이 발생하더라도 reservation이 정리되어야 한다. 특정 예외 타입에만 의존하는 cleanup은 허용되지 않는다. 시스템은 이 동작을 SHALL 보장해야 한다.

#### Scenario: ProxyResponseError 발생 시 release

- **WHEN** `compact_responses()`에서 `ProxyResponseError`가 발생하면
- **THEN** reservation이 release되어야 한다 (SHALL)

#### Scenario: 예상 외 런타임 예외 발생 시 release

- **WHEN** `compact_responses()`에서 `ProxyResponseError` 외의 예외(`Exception`)가 발생하면
- **THEN** reservation이 동일하게 release되어야 한다 (SHALL)

#### Scenario: compact 성공 시 finalize

- **WHEN** `compact_responses()`가 정상 완료되면
- **THEN** `finalize_usage_reservation()`이 호출되어야 한다 (SHALL)

### Requirement: Finalize / Release 멱등성

`finalize_usage_reservation()`과 `release_usage_reservation()`은 이미 정산된(finalized 또는 released) reservation에 대해 안전하게 no-op 처리되어야 한다. 이중 호출이 quota를 이중 반영하거나 에러를 발생시키면 안 된다. 시스템은 이 동작을 SHALL 보장해야 한다.

#### Scenario: finalize 후 release 호출 시 no-op

- **WHEN** reservation이 이미 `finalized` 상태에서 `release_usage_reservation()`이 호출되면
- **THEN** 아무 동작 없이 반환되어야 한다 (SHALL)
- **AND** quota 값이 변경되지 않아야 한다 (SHALL)

#### Scenario: release 후 finalize 호출 시 no-op

- **WHEN** reservation이 이미 `released` 상태에서 `finalize_usage_reservation()`이 호출되면
- **THEN** 아무 동작 없이 반환되어야 한다 (SHALL)
- **AND** quota 값이 변경되지 않아야 한다 (SHALL)

#### Scenario: 동일 finalize 이중 호출 시 1회만 반영

- **WHEN** 동일 `reservation_id`로 `finalize_usage_reservation()`이 2회 호출되면
- **THEN** 사용량은 정확히 1회만 반영되어야 한다 (SHALL)

### Requirement: gpt-5.4-mini pricing is recognized

The system MUST recognize `gpt-5.4-mini` pricing when computing request costs. Snapshot aliases for the same model family MUST resolve to the canonical `gpt-5.4-mini` price table entry.

#### Scenario: gpt-5.4-mini request priced at standard tier

- **WHEN** a request for `gpt-5.4-mini` completes with standard service tier
- **THEN** the system computes non-zero cost using the configured `gpt-5.4-mini` standard rates

#### Scenario: gpt-5.4-mini snapshot request priced at canonical rates

- **WHEN** a request for `gpt-5.4-mini-2026-03-17` completes
- **THEN** the system resolves the snapshot alias to `gpt-5.4-mini`
- **AND** the system applies the same standard rates

### Requirement: API keys can read their own `/v1/usage`

The system SHALL expose `GET /v1/usage` for API-key self-service. It MUST require a valid Bearer API key in `Authorization`, even with `api_key_auth_enabled=false`. Validation failures MUST use the existing `/v1/*` OpenAI error envelope. Responses MUST contain only authenticated-key data.

#### Scenario: Missing API key is rejected

- **WHEN** a client calls `GET /v1/usage` without a Bearer token
- **THEN** the system returns 401 in the OpenAI error format

#### Scenario: Invalid API key is rejected

- **WHEN** a client calls `GET /v1/usage` with an unknown, expired, or inactive Bearer key
- **THEN** the system returns 401 in the OpenAI error format

### Requirement: API key self-usage response fields

`GET /v1/usage` MUST return:
- `request_count`, `total_tokens`, `cached_input_tokens`, `total_cost_usd`.
- `limits[]`: only the authenticated key's configured limits, with `limit_type`, `limit_window`, `max_value`, `current_value`, `remaining_value`, `model_filter`, `reset_at`, `source`.
- `upstream_limits[]`: aggregate upstream Codex credit windows when available, with the same fields and `source: "aggregate"`.

#### Scenario: Key with no usage returns zero totals

- **WHEN** a valid API key with no request-log usage calls `GET /v1/usage`
- **THEN** the system returns `request_count: 0`, `total_tokens: 0`, `cached_input_tokens: 0`, `total_cost_usd: 0.0`

#### Scenario: Usage is scoped to the authenticated key

- **WHEN** multiple API keys have request-log history and one of them calls `GET /v1/usage`
- **THEN** the response includes only the usage totals and limits for that authenticated key

#### Scenario: Upstream limits are separate from API-key limits

- **WHEN** an API key with its own limit calls `GET /v1/usage`
- **AND** upstream Codex aggregate usage data exists
- **THEN** `limits[]` contains the API-key limit values
- **AND** `upstream_limits[]` contains the aggregate Codex credit windows

#### Scenario: Self-usage works while global proxy auth is disabled

- **WHEN** `api_key_auth_enabled` is false and a client calls `GET /v1/usage` with a valid Bearer key
- **THEN** the system still authenticates that key and returns the self-usage payload

### Requirement: API key cost accounting uses the billable service tier
API key cost accounting MUST continue to use the effective billable `service_tier` chosen for the request log and MUST NOT derive pricing from the operator-requested tier when the upstream reports a different actual tier.

#### Scenario: Requested and actual tiers differ
- **WHEN** a priced request is sent with `requested_service_tier: "priority"`
- **AND** the upstream reports `actual_service_tier: "default"`
- **THEN** the persisted billable `service_tier` is `default`
- **AND** API key cost accounting uses the `default` tier rate for that request

### Requirement: API keys can enforce a service tier

The dashboard API key CRUD surface MUST allow callers to persist an optional enforced service tier. The service MUST normalize `fast` to the canonical upstream value `priority` before persistence and before returning the API key payload.

#### Scenario: Create API key with fast service tier alias

- **WHEN** a dashboard client creates an API key with `enforcedServiceTier: "fast"`
- **THEN** the request is accepted
- **AND** the persisted API key stores the canonical value `priority`
- **AND** the response returns `enforcedServiceTier: "priority"`

#### Scenario: Update API key with canonical service tier

- **WHEN** a dashboard client updates an API key with `enforcedServiceTier: "flex"`
- **THEN** the persisted API key stores `flex`
- **AND** subsequent reads return `flex`

### Requirement: API key list includes pooled credit data

`GET /api/api-keys/` SHALL pool per-key upstream usage over selectable assigned accounts, or all selectable accounts if none are assigned. These exclude `paused`/`deactivated`, matching load-balancer routing eligibility. Keys SHALL include `pooled_remaining_percent_primary` and `pooled_remaining_percent_secondary` (float or null), and `pooled_capacity_credits_primary` (float, default 0.0). Zero primary capacity (e.g., all assigned accounts free-tier) SHALL make primary remaining percent null.

#### Scenario: Scoped key pools assigned accounts only

- **WHEN** an API key has `assignedAccountIds` containing two accounts
- **AND** those accounts have usage data
- **THEN** `pooled_remaining_percent_primary` and `pooled_remaining_percent_secondary` reflect only those two accounts

#### Scenario: Unscoped key pools all accounts

- **WHEN** an API key has `assignedAccountIds` = []
- **THEN** pooled credit fields reflect all accounts in the system

#### Scenario: Free-tier accounts hide primary bar

- **WHEN** all assigned accounts have plan_type "free" (primary capacity = 0)
- **THEN** `pooled_capacity_credits_primary` = 0.0
- **AND** `pooled_remaining_percent_primary` = null

#### Scenario: Paused and deactivated accounts are excluded

- **WHEN** an API key has assigned accounts with active and paused statuses
- **THEN** pooled credit fields reflect only the active selectable accounts

### Requirement: API key 7-day usage includes account cost breakdown

`GET /api/api-keys/{key_id}/usage-7d` SHALL return `accountCosts[]` in addition to the existing 7-day totals for the selected API key. Each `accountCosts[]` item SHALL include `accountId`, `email`, `costUsd`, and `isDeleted`.

The system MUST aggregate `accountCosts[]` from request-log rows whose `api_key_id` matches the selected key and whose `requested_at` falls inside the rolling 7-day window used by the endpoint totals.

#### Scenario: Account costs are sorted by descending cost
- **WHEN** a client loads `GET /api/api-keys/{key_id}/usage-7d`
- **AND** multiple grouped account-cost buckets exist in the 7-day window
- **THEN** `accountCosts[]` is ordered by `costUsd` descending

#### Scenario: Unknown account usage remains separate
- **WHEN** request-log rows in the 7-day window have `account_id = NULL`
- **AND** those rows are not soft-deleted
- **THEN** the response includes an `accountCosts[]` item with `accountId: null`, `email: null`, and `isDeleted: false`

#### Scenario: Deleted account usage is grouped into one bucket
- **WHEN** request-log rows in the 7-day window are marked deleted
- **THEN** the response groups their cost into a synthetic `accountCosts[]` item with `accountId: null`, `email: null`, and `isDeleted: true`

#### Scenario: Deleted and unknown account usage stay distinct
- **WHEN** the same API key has both soft-deleted request-log cost and unknown non-deleted request-log cost inside the 7-day window
- **THEN** the response returns separate `accountCosts[]` items for the deleted and non-deleted buckets

### Requirement: API key 7-day account-cost queries use a composite request-log index

The database SHALL provide an index that supports filtering request logs by API key and 7-day requested-at range before grouping by account for the API-key account-cost breakdown.

#### Scenario: Composite account-cost index exists after migration
- **WHEN** database migrations are applied
- **THEN** the `request_logs` table includes an index covering `api_key_id`, descending `requested_at`, and `account_id`

### Requirement: Request-aware API-key usage reservations

API-key admission MUST reserve a bounded request-aware budget, not a fixed 8192 input + 8192 output tokens per request. Token-limit admission MUST reserve request input/output budgets. Self-contained input MAY be estimated. Opaque upstream context MUST use a conservative input budget. Output MUST use a bounded system default unless codex-lb verifies that upstream enforces a client output cap. `cost_usd` reservations MUST use the same token budgets and effective request service tier.

#### Scenario: Concurrent priority lanes do not require 8 × 8192 output-token headroom

- **WHEN** an API key has a `cost_usd` limit with enough remaining value for the bounded request-aware reservations
- **AND** eight `gpt-5.5` requests using `service_tier = "priority"` are admitted concurrently
- **THEN** the proxy allows all eight reservations instead of rejecting a lane solely because the old 8192-output-token pre-charge would exceed the limit

#### Scenario: Opaque input uses conservative input fallback

- **WHEN** a request references input that the proxy cannot size locally, such as `previous_response_id`, `conversation`, `input_file`, or `input_image`
- **THEN** API-key admission uses the conservative default input-token reservation budget for input tokens
- **AND** final accounting still settles to actual completed usage

### Requirement: API-key reservation finalization uses actual usage exactly once

Reservation budgets MUST serve only admission and in-flight accounting. Final accounting MUST settle to authoritative completed usage and service-tier pricing. Finalization MUST adjust every applicable reserved value to actual completed usage exactly once, including limits with zero admission reservations.

#### Scenario: Zero-reservation limits still settle actual usage

- **WHEN** API-key admission records a zero-delta reservation item for an applicable limit
- **AND** the request completes with non-zero actual usage for that limit
- **THEN** reservation finalization increments the limit by the actual usage instead of skipping the limit

### Requirement: Map `auto`/`default` enforced service tier to outbound omission
API-key `enforced_service_tier` accepts `auto`, `default`, `priority`, `flex`, and `fast` (alias for `priority`). The proxy MUST omit outbound `service_tier` (`None`) for enforced `auto`/`default`, not forward literal strings. The ChatGPT/Codex backend rejects those literals because both mean "let upstream pick". Enforced `priority`/`flex` MUST be forwarded unchanged.

#### Scenario: Enforced service tier is `default`
- **WHEN** a request is processed under an API key with `enforced_service_tier = "default"`
- **THEN** the outbound `service_tier` field is absent

#### Scenario: Enforced service tier is `auto`
- **WHEN** a request is processed under an API key with `enforced_service_tier = "auto"`
- **THEN** the outbound `service_tier` field is absent

#### Scenario: Enforced service tier is a real upstream tier
- **WHEN** a request is processed under an API key with `enforced_service_tier = "priority"` or `"flex"`
- **THEN** the outbound `service_tier` field equals the enforced value

### Requirement: API key allowlist allows Cursor aliases

The model allowlist check MUST treat supported Cursor-style GPT-5 aliases as equivalent to their
canonical GPT model when deciding access. A request for the canonical model must be allowed when the key
stores a compatible alias in `allowed_models`.

#### Scenario: Cursor alias allowed model permits canonical request

- **WHEN** a key has `allowed_models: ["gpt-5.4-mini-high"]`
- **AND** a request is made for model `gpt-5.4-mini`
- **THEN** the proxy permits the request because the allowed alias resolves to the requested canonical model

### Requirement: Model catalogs must expose canonical models for alias allowlists

When API-key model allowlists include Cursor-style aliases, the visible model lists MUST expose canonical model IDs and
omit alias-only synthetic IDs so clients see stable model names.

#### Scenario: Model list canonicalizes Cursor aliases

- **WHEN** a key with `allowed_models: ["gpt-5.4-mini-high"]` and `enforced_model: "gpt-5.4-mini-high"` calls `GET /v1/models`
- **THEN** the response contains the canonical model `gpt-5.4-mini`
- **AND** the response does not expose a synthetic `gpt-5.4-mini-high` model id

#### Scenario: Codex model list visibility canonicalizes Cursor aliases

- **WHEN** a key with `allowed_models: ["gpt-5.4-mini-high"]`, `enforced_model: "gpt-5.4-mini-high"`, and `apply_to_codex_model=true` calls `GET /backend-api/codex/models`
- **THEN** the canonical `gpt-5.4-mini` entry is visible with `visibility: "list"`
- **AND** other entries are hidden according to the API key allowlist policy

### Requirement: Untrusted forwarded headers do not grant unauthenticated proxy locality

When API-key authentication is disabled and proxy-header trust is enabled, forwarded client-IP headers from a socket peer outside every configured trusted-proxy CIDR MUST NOT cause a protected proxy request to be classified as local. Such a request MUST remain blocked unless its raw socket peer independently matches `proxy_unauthenticated_client_cidrs`.

#### Scenario: Untrusted loopback proxy remains blocked

- **WHEN** API-key authentication is disabled
- **AND** proxy-header trust is enabled
- **AND** the raw loopback socket peer is outside every configured trusted-proxy CIDR
- **AND** a forwarded client-IP header is present
- **AND** the raw socket peer is outside `proxy_unauthenticated_client_cidrs`
- **THEN** the protected proxy request is rejected with HTTP 401

#### Scenario: Explicit raw-socket allowlist remains authoritative

- **WHEN** the raw socket peer belongs to `proxy_unauthenticated_client_cidrs`
- **THEN** the protected proxy request may proceed without API-key authentication
- **AND** forwarded header contents do not determine that allowlist match

### Requirement: Direct-local proxy access inspects every forwarded client hint field

When API-key authentication and proxy-header trust are disabled, a loopback socket peer MUST qualify for direct-local protected proxy access only when no non-empty forwarded client-IP field value is present. The system MUST inspect every repeated field value; a later non-empty value MUST keep the request blocked unless the raw socket peer independently matches `proxy_unauthenticated_client_cidrs`.

#### Scenario: Later duplicate forwarded hint remains unauthorized

- **WHEN** API-key authentication and proxy-header trust are disabled
- **AND** a loopback request contains an empty `X-Forwarded-For` field followed by a non-empty `X-Forwarded-For` field
- **AND** the raw socket peer is outside `proxy_unauthenticated_client_cidrs`
- **THEN** the protected proxy request is rejected with HTTP 401

### Requirement: GPT-5.6 usage cost pricing matches the current published rates

Canonical GPT-5.6 API-key usage, request-log, reservation, and aggregate costs MUST use these USD/1M input/cached-input/output token rates:

| Model | Standard | Fast/priority | Flex | Standard long context |
| --- | --- | --- | --- | --- |
| `gpt-5.6-sol` | `5/0.50/30` | `10/1/60` | `2.5/0.25/15` | `10/1/45` |
| `gpt-5.6-terra` | `2/0.20/12` | `4/0.40/24` | `1/0.10/6` | `4/0.40/18` |
| `gpt-5.6-luna` | `0.20/0.02/1.20` | `0.40/0.04/2.40` | `0.10/0.01/0.60` | `0.40/0.04/1.80` |

#### Scenario: Terra standard usage uses the current rate

- **WHEN** a standard-tier `gpt-5.6-terra` request has 200,000 input tokens and 1,000,000 output tokens
- **THEN** the token cost is `$12.40`

#### Scenario: Luna Fast and Flex usage use their tier rates

- **WHEN** a `gpt-5.6-luna` request has 200,000 input tokens, 100,000 cached input tokens, and 1,000,000 output tokens
- **AND** the request uses `priority` or `fast`
- **THEN** the token cost is `$2.444`
- **WHEN** the same usage uses `flex`
- **THEN** the token cost is `$0.611`

### Requirement: GPT-5.6 pricing aliases and long-context rules

For GPT-5.6, `priority`/`fast` MUST use Fast/priority rates. Standard long-context rates MUST apply only above 272,000 input tokens. Flex long-context pricing MUST retain existing Flex short-context rates and multipliers. Version/snapshot model aliases MUST resolve to the corresponding canonical table entry. Batch and cache-write rates MUST NOT enter this contract without corresponding proxy request and usage fields.

#### Scenario: Terra standard long-context usage uses the current long-context rate

- **WHEN** a standard-tier `gpt-5.6-terra` request has 300,000 input tokens, 50,000 cached input tokens, and 100,000 output tokens
- **THEN** the token cost is `$2.82`

#### Scenario: Versioned aliases use canonical GPT-5.6 pricing

- **WHEN** the requested model is `gpt-5.6-luna-2026-07-13`
- **THEN** cost accounting resolves it to the `gpt-5.6-luna` price entry

### Requirement: One-time API-key secret responses prevent storage

Every successful response containing a full plain API key MUST include `Cache-Control: no-store, no-cache, must-revalidate, private`, `Pragma: no-cache`, and `Expires: 0`. This applies to the canonical create URL (`POST /api/api-keys/`) and regeneration. The policy MUST NOT alter payload, generation, persistence, authorization, errors, or logging; plain keys MUST remain absent from logs.

#### Scenario: Create through the canonical collection URL

- **WHEN** an authorized admin creates a key through `POST /api/api-keys/`
- **THEN** all three directives are present
- **AND** the existing one-time plain-key payload remains

#### Scenario: Regenerate a key

- **WHEN** an authorized admin regenerates a key
- **THEN** all three directives are present
- **AND** the existing regenerated-key payload remains

#### Scenario: Unauthorized write stays rejected

- **WHEN** a read-only principal attempts create or regenerate
- **THEN** existing 403 behavior remains
- **AND** no plain key or secret-response headers are returned

### Requirement: Keyed owner-unavailable streams settle before account health

Default stream API-key settlement MUST await in the request/response path, not detach. Cancellation MAY transfer tracked cleanup. Before account-health writes, finalizers MUST await settlement commit (fallback release commit on failure) at keyed websocket health-error endings or keyed HTTP SSE failures rewritten to `previous_response_owner_unavailable` or terminal queues draining empty before terminal health/success. Without confirmation, health writes and deferred penalties MUST stay unapplied.

#### Scenario: Websocket health-error settlement precedes the health write

- **GIVEN** a keyed websocket stream that terminates with an account-health error
- **WHEN** the finalizer settles the reservation
- **THEN** it waits for the settlement to commit before recording the account-health error

#### Scenario: Owner-unavailable rewrite settles before health

- **GIVEN** a keyed HTTP SSE stream rewrites an upstream failure to `previous_response_owner_unavailable`
- **WHEN** the stream records account-health recovery for the original failure
- **THEN** reservation settlement or fail-safe release confirms first

#### Scenario: Empty terminal queue settles before health or success

- **GIVEN** a keyed HTTP SSE bridge queue drains empty on a terminal path
- **WHEN** the stream records terminal account health or success
- **THEN** reservation settlement or fail-safe release confirms first

#### Scenario: Unconfirmed settlement leaves health unapplied

- **GIVEN** a keyed websocket or HTTP SSE stream reaches an ordering-sensitive terminal path
- **WHEN** both primary settlement and fallback release fail
- **THEN** the stream does not record account health
- **AND** any deferred penalty remains unapplied
