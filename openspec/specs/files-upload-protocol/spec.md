# files-upload-protocol Specification

## Purpose
Describe native Codex file upload registration and finalization, including authentication, account selection, bounded polling, and request logging.
## Requirements
### Requirement: Native file upload registration endpoint

Authenticated `POST /backend-api/files` SHALL proxy Codex uploads, accepting JSON `file_name` (non-empty string), `file_size` (positive integer ≤ 512 MiB / `OPENAI_FILE_UPLOAD_LIMIT_BYTES`) and `use_case` (string, default `"codex"`). It MUST forward to upstream `POST /files` with the selected account's Bearer token and `chatgpt-account-id`, returning JSON (including `file_id`, Azure Blob `upload_url`) verbatim. It MUST NOT proxy or rewrite the SAS upload URL; clients PUT bytes directly to it.

#### Scenario: Native file create request is forwarded

- **WHEN** an authenticated client posts a valid `{file_name, file_size, use_case}` body to `/backend-api/files`
- **THEN** the service forwards the JSON body to upstream `POST /files` with the selected account's Bearer token and `chatgpt-account-id`
- **AND** returns the upstream response JSON verbatim with HTTP status 200

#### Scenario: File-size cap is enforced at the edge

- **WHEN** a client requests `file_size` greater than 512 MiB
- **THEN** the service returns HTTP 400 with an OpenAI-format `invalid_request_error` envelope
- **AND** does not call upstream

#### Scenario: Upstream registration error is propagated

- **WHEN** upstream `POST /files` returns a non-2xx response
- **THEN** the service returns the same HTTP status and an OpenAI-format error envelope derived from the upstream payload

#### Scenario: Use-case defaults to codex when omitted

- **WHEN** a client omits the `use_case` field
- **THEN** the service forwards `use_case = "codex"` to upstream

### Requirement: File finalize / status polling endpoint

Authenticated `POST /backend-api/files/{file_id}/uploaded` SHALL finalize uploads. It MUST accept non-empty `file_id` and empty JSON body, forwarding to upstream `POST /files/{file_id}/uploaded`. Codex CLI-style polling MUST run server-side every 250 ms while `status == "retry"`, for ≤30 s total, then return latest payload at any status. `success`/`failed` MUST return immediately. Upstream JSON (`status`, `download_url`, `file_name`, `mime_type`, `file_size_bytes` included) MUST return verbatim.

#### Scenario: Finalize returns success on first poll

- **WHEN** upstream returns `status: success` on the first call
- **THEN** the service returns HTTP 200 with that payload and does not poll again

#### Scenario: Finalize loops on retry status until success

- **WHEN** upstream returns `status: retry` followed by `status: success`
- **THEN** the service polls every 250 ms and returns the eventual `success` payload verbatim

#### Scenario: Finalize budget bounds the retry loop

- **WHEN** upstream returns `status: retry` for the entire 30 s budget
- **THEN** the service returns HTTP 200 with the last `status: retry` payload so the caller can decide what to do
- **AND** does not block beyond the configured budget

#### Scenario: Finalize maps upstream error status

- **WHEN** upstream returns 404 for an unknown `file_id`
- **THEN** the service returns HTTP 404 with an OpenAI-format error envelope

### Requirement: File proxy routes share account-selection and request-log plumbing

File proxy routes MUST use `/backend-api/transcribe`'s load-balancer / freshness / 401-retry account-selection pattern and persist a request-log entry on every attempt. Logs MUST use synthetic models `files-create` for `POST /backend-api/files` and `files-finalize` for `POST /backend-api/files/{file_id}/uploaded`. Transport MUST be recorded as HTTP. File requests MUST NOT count against per-model API key limits unless the key explicitly allows the synthetic model identifiers.

#### Scenario: 401 from upstream triggers forced refresh and one retry

- **WHEN** upstream `POST /files` returns 401 on the first attempt
- **THEN** the service forces a token refresh and retries once with the refreshed account metadata

#### Scenario: Request-log entry is written for both success and failure

- **WHEN** any `/backend-api/files` or `/backend-api/files/{id}/uploaded` request completes (success or error)
- **THEN** a request-log row is persisted with model `files-create` or `files-finalize`, transport `http`, and the appropriate status / error code

### Requirement: File create and finalize routes require API key authentication when enforcement is enabled

File routes MUST use the same `validate_proxy_api_key` and dashboard `apiKeyAuthEnabled` gating as `/backend-api/transcribe`. With API key auth enabled, requests without a valid API key MUST return HTTP 401 with an OpenAI-format `invalid_api_key` error.

#### Scenario: File create is rejected without API key when auth enforcement is on

- **WHEN** dashboard `apiKeyAuthEnabled` is true and a client posts to `/backend-api/files` without a valid API key
- **THEN** the service returns HTTP 401 with `error.code = "invalid_api_key"`

#### Scenario: File finalize is rejected without API key when auth enforcement is on

- **WHEN** dashboard `apiKeyAuthEnabled` is true and a client posts to `/backend-api/files/{file_id}/uploaded` without a valid API key
- **THEN** the service returns HTTP 401 with `error.code = "invalid_api_key"`

