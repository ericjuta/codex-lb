# responses-api-compat Specification

## Purpose

See context docs for background.
## Requirements
### Requirement: Use prompt_cache_key as OpenAI cache affinity
For OpenAI-style `/v1/responses`, `/v1/responses/compact`, and chat-completions requests mapped onto Responses, the service MUST treat a non-empty `prompt_cache_key` as a bounded upstream account affinity key for prompt-cache correctness. This affinity MUST apply even when dashboard `sticky_threads_enabled` is disabled, the service MUST continue forwarding the same `prompt_cache_key` upstream unchanged, and the stored affinity MUST expire after the configured freshness window so older keys can rebalance. The freshness window MUST come from dashboard settings so operators can adjust it without restart.

#### Scenario: dashboard prompt-cache affinity TTL is applied
- **WHEN** an operator updates the dashboard prompt-cache affinity TTL
- **THEN** subsequent OpenAI-style prompt-cache affinity decisions use the new freshness window

### Requirement: Native `/backend-api/codex` routes accept the Codex tool surface
The service MUST accept native `/backend-api/codex/responses` HTTP and websocket requests that include the Codex Desktop tool surface. This includes custom tools plus built-in Codex tool types such as `image_generation`, `file_search`, `code_interpreter`, and `computer_use_preview`. The service MUST continue normalizing `web_search_preview` to `web_search` before forwarding upstream. OpenAI-style `/v1/*` routes MUST keep rejecting unsupported built-in tools with an invalid_request_error.

#### Scenario: backend responses accept native built-in and custom tools
- **WHEN** a client sends `/backend-api/codex/responses` with tools including `{"type":"custom","name":"exec"}` and `{"type":"image_generation"}`
- **THEN** the service accepts the request and forwards the tools upstream without returning an invalid_request_error

#### Scenario: v1 responses continue rejecting unsupported built-in tools
- **WHEN** a client sends `/v1/responses` with `tools=[{"type":"image_generation"}]`
- **THEN** the service returns a 4xx OpenAI invalid_request_error indicating the unsupported tool type

### Requirement: Bridge-enabled worker pools use addressable bridge owners

When the HTTP responses session bridge is enabled and the configured runtime worker count is greater than one, the service MUST NOT start a plain Uvicorn multi-worker process group with a shared bridge instance id. It MUST instead start a front listener plus single-worker backend processes where each backend has a unique bridge instance id and an advertised endpoint that can route owner handoff to that worker-local bridge session map.

#### Scenario: bridge-enabled multi-worker startup uses addressable workers

- **WHEN** the HTTP responses session bridge is enabled
- **AND** the configured worker count is greater than one
- **THEN** startup launches single-worker backend app processes with unique bridge instance ids
- **AND** each backend advertises a worker-specific bridge endpoint
- **AND** public HTTP and WebSocket traffic enters through one front listener

#### Scenario: bridge-disabled multi-worker startup remains plain Uvicorn

- **WHEN** the HTTP responses session bridge is disabled
- **AND** the configured worker count is greater than one
- **THEN** startup continues to pass the requested worker count directly to Uvicorn
