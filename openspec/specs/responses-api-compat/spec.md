# responses-api-compat Specification

## Purpose

Define Responses API compatibility contracts so Codex, OpenCode, and OpenAI-style clients preserve expected behavior.
## Requirements
### Requirement: Internal Responses Lite header is forwarded upstream

The service MUST preserve an inbound `X-OpenAI-Internal-Codex-Responses-Lite` header when calling upstream Responses, compact, or WebSocket transports. The service MUST preserve the header value and MUST NOT disable Responses Lite behavior by removing the header.

#### Scenario: HTTP and compact upstream headers preserve Lite

- **WHEN** a client sends a Responses or compact request with `X-OpenAI-Internal-Codex-Responses-Lite: 1`
- **THEN** the upstream HTTP request headers include `X-OpenAI-Internal-Codex-Responses-Lite: 1`
- **AND** existing authentication, proxy identity, and hop-by-hop header filtering remains in effect

#### Scenario: WebSocket upstream headers preserve Lite

- **WHEN** a client opens a Responses WebSocket with `X-OpenAI-Internal-Codex-Responses-Lite: 1`
- **THEN** the upstream WebSocket connection headers include `X-OpenAI-Internal-Codex-Responses-Lite: 1`
- **AND** existing WebSocket beta and Codex continuity headers are preserved

### Requirement: GPT-5.6 bootstrap metadata advertises Lite Code Mode capabilities

When the static bootstrap catalog is serving `gpt-5.6-sol`, `gpt-5.6-terra`, or `gpt-5.6-luna`, the Codex model metadata MUST include `use_responses_lite=true`, `tool_mode=code_mode_only`, and `experimental_supported_tools=["exec", "wait"]`. The `multi_agent_version` MUST be `v2` for Sol and Terra and `v1` for Luna. A successful live model-catalog refresh MAY replace these fallback entries with upstream metadata.

#### Scenario: Offline GPT-5.6 model discovery preserves tool capabilities

- **GIVEN** the live upstream model catalog has not populated the registry
- **WHEN** a client requests `/backend-api/codex/models`
- **THEN** the GPT-5.6 Sol, Terra, and Luna entries include the Lite and Code Mode capability metadata
- **AND** each entry advertises `exec` and `wait` as experimental supported tools
- **AND** the entries retain their configured multi-agent version

### Requirement: Responses Lite tool definitions survive input normalization

When a Responses Lite request contains an input item with `type: "additional_tools"`, the service MUST preserve that item, including its `role` and complete `tools` array, in the upstream request payload. Instruction normalization MUST NOT move it into top-level `instructions` or drop it because it has no textual content.

#### Scenario: Codex Code Mode tools reach upstream

- **WHEN** a Codex client sends a Responses Lite request whose input contains a developer `additional_tools` item with `exec` and `wait` definitions
- **THEN** the normalized upstream payload contains the same `additional_tools` item
- **AND** the item retains the complete `exec` and `wait` tool definitions
- **AND** ordinary textual system and developer messages continue to merge into top-level `instructions`

#### Scenario: Tool definitions are not mistaken for developer instructions

- **WHEN** an `additional_tools` item has no textual content
- **THEN** it is not removed as an empty developer instruction item
- **AND** it remains in its original position relative to the other input items

### Requirement: Use prompt_cache_key as OpenAI cache affinity
For OpenAI-style `/v1/responses`, `/v1/responses/compact`, and chat-completions requests mapped onto Responses, the service MUST treat a non-empty `prompt_cache_key` as the bounded upstream account affinity key for prompt-cache correctness even when a `session_id` header is present. OpenAI-style route wiring MUST NOT upgrade those requests to durable `CODEX_SESSION` affinity by default. This affinity MUST apply even when dashboard `sticky_threads_enabled` is disabled, the service MUST continue forwarding the same `prompt_cache_key` upstream unchanged, and the stored affinity MUST expire after the configured freshness window so older keys can rebalance. The freshness window MUST come from dashboard settings so operators can adjust it without restart.

#### Scenario: OpenAI-style route ignores session header for durable codex-session pinning
- **WHEN** a client sends `/v1/responses` or `/v1/responses/compact` with a non-empty `session_id` header and no explicit sticky-thread mode
- **THEN** the service does not persist a durable `codex_session` mapping solely from that header
- **AND** bounded prompt-cache affinity behavior remains in effect

#### Scenario: dashboard prompt-cache affinity TTL is applied
- **WHEN** an operator updates the dashboard prompt-cache affinity TTL
- **THEN** subsequent OpenAI-style prompt-cache affinity decisions use the new freshness window

### Requirement: Responses requests reject uploaded input_image references

The system SHALL accept `{"type":"input_file","file_id":"file_*"}` attached-file items in `/v1/responses`, `/backend-api/codex/responses`, and `/responses/compact` request payloads and forward them verbatim.

When an `input_image` part contains a `file_id` field or an `image_url` starting with `sediment://`, the proxy MUST return HTTP 400 with `error.code = "unsupported_input_image_format"` and an explanation that the upstream Responses API only accepts inline `data:` URLs for `input_image`. The proxy MUST NOT fetch the upload, MUST NOT inline-convert the image, and MUST NOT trim, slim, or rewrite any conversation content.

`app/core/openai/requests.py::extract_input_image_file_references` MAY be used to detect the unsupported shape. This request path MUST NOT fetch uploads, inline-convert images, or otherwise reshape inbound conversation payloads.

#### Scenario: input_image file_id is rejected before forwarding

- **WHEN** a `/v1/responses` request contains `{"type":"input_image","file_id":"file_img"}`
- **THEN** the proxy returns HTTP 400 with `error.code = "unsupported_input_image_format"`
- **AND** the response explains that inline `data:` URLs are the supported `input_image` contract

#### Scenario: sediment upload URL is rejected before forwarding

- **WHEN** a `/responses/compact` request contains `{"type":"input_image","image_url":"sediment://file_img"}`
- **THEN** the proxy returns HTTP 400 with `error.code = "unsupported_input_image_format"`
- **AND** does not fetch or inline-convert the upload

#### Scenario: large request payload routes via HTTP transport on auto
- **GIVEN** `upstream_stream_transport` is `"auto"` and the request payload size exceeds the WebSocket frame budget
- **WHEN** the proxy resolves the upstream transport
- **THEN** the request MUST be sent over HTTP `POST` instead of WebSocket
- **AND** explicit `upstream_stream_transport = "websocket"` overrides MUST still take precedence

#### Scenario: large request payload bypasses the HTTP responses bridge
- **GIVEN** the HTTP responses bridge is enabled and the request payload exceeds the WebSocket frame budget
- **WHEN** the proxy receives a `/v1/responses`, `/backend-api/codex/responses`, or `/responses/compact` request
- **THEN** the bridge MUST be bypassed for that request and the request MUST be sent over raw HTTP
- **AND** subsequent smaller requests MUST continue to use the bridge normally

### Requirement: Oversized responses request payloads fall back to HTTP
When `upstream_stream_transport` is `"auto"` and the serialized request payload size exceeds the WebSocket frame budget, the proxy MUST use upstream HTTP `POST` instead of WebSocket. If the HTTP responses bridge is enabled and the same oversized request would otherwise route through the bridge, the proxy MUST bypass the bridge for that request only and send it over raw HTTP. Explicit `upstream_stream_transport` overrides MUST still take precedence.

#### Scenario: large request payload routes via HTTP transport on auto
- **GIVEN** `upstream_stream_transport` is `"auto"` and the request payload size exceeds the WebSocket frame budget
- **WHEN** the proxy resolves the upstream transport
- **THEN** the request MUST be sent over HTTP `POST` instead of WebSocket
- **AND** explicit `upstream_stream_transport = "websocket"` overrides MUST still take precedence

#### Scenario: large request payload bypasses the HTTP responses bridge
- **GIVEN** the HTTP responses bridge is enabled and the request payload exceeds the WebSocket frame budget
- **WHEN** the proxy receives a `/v1/responses`, `/backend-api/codex/responses`, or `/responses/compact` request
- **THEN** the bridge MUST be bypassed for that request and the request MUST be sent over raw HTTP
- **AND** subsequent smaller requests MUST continue to use the bridge normally

### Requirement: Clean upstream close before any response event fails fast

When the HTTP responses bridge observes an upstream websocket close with `close_code = 1000` before any `response.*` event has been surfaced for the pending request, the proxy MUST classify the close as rejected input, surface HTTP 502 `upstream_rejected_input`, and MUST NOT trigger `retry_precreated` or `retry_fresh_upstream`.

#### Scenario: clean close before response.created is not retried

- **WHEN** upstream closes the HTTP responses bridge with `close_code = 1000` before any `response.*` event for the pending request
- **THEN** the proxy returns HTTP 502 with `error.code = "upstream_rejected_input"`
- **AND** does not transparently replay the pre-created request

### Requirement: Long Codex websocket turns tolerate extended upstream silence
The default compact request budget MUST be at least 180 seconds, and the default upstream stream idle timeout MUST be at least 600 seconds, so long-running Codex turns can survive expensive compaction or tool execution without a local proxy watchdog ending the turn prematurely.

#### Scenario: compact and stream watchdog defaults leave room for long turns
- **WHEN** the service starts with default configuration
- **THEN** `compact_request_budget_seconds` is at least 180 seconds
- **AND** `stream_idle_timeout_seconds` is at least 600 seconds

### Requirement: Upstream websocket drops penalize affected accounts

When an upstream websocket closes while one or more streamed response requests are pending and have not reached a terminal event, the proxy MUST record a transient upstream error for the account before signaling failure for those pending requests, except when the close carries a classified process-wide network failure. A classified process-wide network failure MUST remain account neutral and use its network error code. For other closes, the proxy MUST surface `stream_incomplete` to affected pending requests except when a direct Responses WebSocket request has already successfully emitted a finite integer `sequence_number`. For that sequenced direct-WebSocket case, the proxy MUST record the request outcome as `stream_incomplete` without emitting a synthetic terminal frame under the active response id, then MUST close the downstream WebSocket with code 1011, unless the request satisfies the verified no-generation prewarm recovery contract below and its one-shot replay succeeds.

#### Scenario: websocket closes before pending responses complete

- **GIVEN** a streamed response request is pending on an upstream websocket
- **AND** the direct downstream response has not emitted a numeric sequence, or
  the request uses another transport
- **WHEN** the websocket closes before a terminal response event is observed
- **AND** the close does not carry a classified process-wide network failure
- **THEN** the pending request fails with `stream_incomplete`
- **AND** the account receives a transient upstream failure signal for routing

#### Scenario: ordinary sequenced direct websocket closes before completion

- **GIVEN** a direct Responses WebSocket request has successfully emitted a
  finite integer `sequence_number`
- **AND** the request does not satisfy the verified no-generation prewarm
  recovery contract
- **WHEN** the upstream websocket closes before a terminal response event is
  observed
- **THEN** the request is recorded as failed with `stream_incomplete`
- **AND** no synthetic terminal frame is emitted under the active response id
- **AND** the downstream WebSocket closes with code 1011
- **AND** the account receives a transient upstream failure signal for routing

#### Scenario: created-only generate-false Codex prewarm recovers

- **GIVEN** a direct Responses WebSocket request is classified by Codex turn
  metadata as `request_kind = "prewarm"`
- **AND** its normalized request body contains `generate = false`
- **AND** only `response.created` at numeric sequence `0` has been sent
  downstream, with no other response progress or visible output
- **WHEN** the upstream websocket closes before the terminal event
- **THEN** the proxy MAY perform the existing bounded one-shot replay
- **AND** it suppresses the replayed `response.created`
- **AND** it forwards only replay numeric sequences that advance beyond `0`
- **AND** the recovered request is finalized and logged exactly once

### Requirement: Single HTTP bridge previous-response misses recover or fail closed
When an HTTP bridge session receives an anonymous upstream `previous_response_not_found` error for a single pending follow-up request, the service MUST treat the error as an internal continuity-loss signal. It MUST either recover through the existing previous-response rebind path or rewrite the error to a retryable continuity failure instead of forwarding the raw upstream invalid-request error.

#### Scenario: single pending HTTP bridge follow-up loses previous-response continuity
- **WHEN** an HTTP `/v1/responses` or `/backend-api/codex/responses` bridge session has exactly one pending request with `previous_response_id`
- **AND** upstream emits `previous_response_not_found` without a `response.id`
- **THEN** the service attempts the existing previous-response recovery path
- **AND** if recovery is unavailable, it emits a retryable continuity failure for that request
- **AND** the downstream error code is not `previous_response_not_found`

### Requirement: WebSocket full-resend previous-response misses retry without stale anchor
When a direct WebSocket `response.create` request includes both `previous_response_id` and a self-contained full resend payload, the service MUST retain a safe replay body without `previous_response_id`. If upstream rejects the anchor with `previous_response_not_found` before `response.created`, the service MUST reconnect and replay the retained full payload as a fresh turn instead of forwarding the raw upstream invalid-request error. A payload that only carries incremental tool outputs for tool calls that are not also present in the same request is not self-contained and MUST NOT be replayed as a fresh turn without `previous_response_id`.

#### Scenario: full-resend WebSocket follow-up loses just-completed anchor
- **WHEN** a WebSocket `/v1/responses` or `/backend-api/codex/responses` follow-up has `previous_response_id`
- **AND** the request payload also carries enough input to be treated as a full resend
- **AND** upstream emits `previous_response_not_found` before assigning a response id
- **THEN** the service reconnects the upstream WebSocket
- **AND** it replays the same request without `previous_response_id`
- **AND** the downstream client receives the recovered response events, not the raw `previous_response_not_found` error

#### Scenario: output-only WebSocket tool delta is not replayed as a fresh turn
- **WHEN** a WebSocket `/v1/responses` or `/backend-api/codex/responses` follow-up has `previous_response_id`
- **AND** the request payload carries `function_call_output`, `custom_tool_call_output`, or `apply_patch_call_output` items without their matching tool-call items in the same payload
- **AND** upstream emits `previous_response_not_found` before assigning a response id
- **THEN** the service MUST NOT replay that payload as a fresh turn without `previous_response_id`
- **AND** the downstream client receives a retryable continuity failure rather than a fabricated fresh turn


### Requirement: Compact trimming preserves prioritised historical side effects

The service MUST retain recognised historical side-effect tool calls as bounded
priority context when an oversized compact input is trimmed. It MUST use the
same side-effect classifier as downstream replay
deduplication. This includes code-mode `exec` and `collaboration` wrapper calls
as well as their lower-level tool spellings and recognised parallel batches.

For each retained historical side effect, compact trimming MUST retain its
matching call and output together. The service MUST reserve space for that
complete pair before selecting optional ordinary head or tail context. Required
state anchors and the current required item remain mandatory; if they leave no
room for a historical pair, the service MAY drop that pair together and retain a
trim marker instead.

A recognised side-effect call without a non-empty `call_id` MUST NOT be
retained as a historical side-effect anchor, because it cannot form a verified
call/output pair.


#### Scenario: Code-mode side effect survives an oversized compact input

- **WHEN** an oversized compact input contains a historical custom `exec` or
  `collaboration` call with its matching output outside required state context
- **THEN** the trimmed upstream input retains both the call and its output when
  the pair fits with required state
- **AND** optional ordinary tail context is dropped before that pair


#### Scenario: Historical side-effect pair cannot fit with required state

- **WHEN** required state anchors and the current required item leave no room
  for a historical side-effect call and its matching output
- **THEN** compact trimming drops the entire historical pair
- **AND** it does not retain only one member of that pair


#### Scenario: Side-effect call lacks a usable pair key

- **WHEN** an oversized compact input contains a recognised historical
  side-effect call without a non-empty `call_id`
- **THEN** compact trimming does not preserve that call as a side-effect anchor
- **AND** it does not emit an unpaired historical side-effect call upstream

### Requirement: Public Responses errors mask previous-response misses
Public Responses endpoints MUST NOT return an OpenAI-shaped `previous_response_not_found` error to clients. If a lower layer still raises or collects that error, the API layer MUST rewrite it to a retryable `stream_incomplete` continuity failure and remove the missing response id from the public payload.

#### Scenario: API layer receives an upstream previous-response miss
- **WHEN** a public `/responses`, `/v1/responses`, `/responses/compact`, or `/v1/responses/compact` handler receives an error with `code=previous_response_not_found`
- **OR** it receives `code=invalid_request_error` with `param=previous_response_id` and a message saying the previous response was not found
- **THEN** the response status is retryable
- **AND** the public error code is `stream_incomplete`
- **AND** the missing `previous_response_id` is not exposed in the response body

### Requirement: Public /v1 responses SSE stream emits only OpenAI Responses contract events
When serving streaming `POST /v1/responses`, the service MUST emit only event types defined by the OpenAI Responses SSE contract (the `response.*` and `error` families) on the public stream. The service MUST drop any vendor-internal event types — specifically, any event whose `type` begins with `codex.` (for example `codex.rate_limits`) — before they reach the public stream. The `/backend-api/codex/*` routes are NOT subject to this requirement and MUST continue forwarding these events unchanged.

#### Scenario: Codex-internal rate-limit event is dropped before response.created
- **WHEN** the upstream Codex backend emits `codex.rate_limits` before `response.created` for a streaming `/v1/responses` request
- **THEN** the public stream MUST NOT contain the `codex.rate_limits` event
- **AND** the first event the public stream emits MUST be `response.created`

#### Scenario: Codex-internal events on the Codex CLI route are preserved
- **WHEN** the upstream emits `codex.rate_limits` for a `POST /backend-api/codex/responses` request
- **THEN** the response stream forwards the `codex.rate_limits` event to the Codex CLI client unchanged

### Requirement: Streamed /v1 responses terminal output is backfilled from item events
When serving streaming `POST /v1/responses`, if the upstream's terminal `response.completed` or `response.incomplete` event carries `output` as missing or as an empty list, the service MUST reconstruct `output` from the `response.output_item.done` events emitted earlier in the same stream before yielding the terminal SSE event. The reconstructed `output` MUST preserve the `output_index` ordering and the raw item payloads. When the terminal `response.completed` / `response.incomplete` already carries a non-empty `output`, the service MUST forward it unchanged.

#### Scenario: Terminal response.completed with empty output is backfilled from streamed items
- **GIVEN** the upstream emits `response.output_item.done` events with valid message or function-call items
- **WHEN** the upstream's terminal `response.completed` event carries `output: []`
- **THEN** the public stream's terminal `response.completed` event MUST carry the reconstructed `output` array, populated from the streamed `output_item.done` items in `output_index` order
- **AND** an OpenAI Python SDK consumer calling `stream.get_final_response().output` MUST receive the same populated list

#### Scenario: Terminal response.completed already carries output
- **WHEN** the upstream's terminal `response.completed` event already includes a non-empty `output` array
- **THEN** the public stream's terminal event MUST carry that `output` array unchanged

### Requirement: Public /v1 responses SSE stream starts with response.created
When serving streaming `POST /v1/responses`, the first OpenAI-contract event the public stream emits MUST be `response.created`. When the upstream's first standard `response.*` event is not `response.created` (for example when the Codex backend jumps directly to `response.failed` on upstream rejection mid-stream), the service MUST synthesize a `response.created` SSE event from the source event's `response` envelope and emit it before forwarding the source event, so that consumers using the OpenAI Python SDK's `responses.stream(...)` parser do not raise `RuntimeError`.

#### Scenario: Upstream error stream that skips response.created is repaired
- **WHEN** the upstream's first standard event is `response.failed` (no preceding `response.created`)
- **THEN** the public stream MUST emit a synthesized `response.created` event derived from the failed event's `response` envelope before forwarding the `response.failed` event
- **AND** an OpenAI Python SDK consumer iterating the stream MUST NOT raise `RuntimeError` from the parser's initial-response check

#### Scenario: Normal stream is not double-emitted
- **WHEN** the upstream's first standard event is already `response.created`
- **THEN** the public stream MUST emit exactly one `response.created` event (no synthesized duplicate)

### Requirement: Upstream overload envelopes are classified as retryable transient failures

When `classify_upstream_failure` observes an upstream error envelope whose `code` is `overloaded_error` or `server_is_overloaded`, the system MUST treat it as `retryable_transient` regardless of the accompanying HTTP status. Streamed Responses API traffic can deliver the overload envelope on a connection that has already returned HTTP 200, so a 5xx-only heuristic is insufficient to drive account fail-over and bounded retry.

#### Scenario: `overloaded_error` without a 5xx status is retryable transient

- **WHEN** `classify_upstream_failure` is called with `error_code="overloaded_error"` and `http_status` not in the 5xx range (including `None`)
- **THEN** the returned `failure_class` is `retryable_transient`
- **AND** the failover layer is eligible to retry the request or fail over to another account instead of returning a non-retryable error to the client

#### Scenario: `overloaded_error` with a 5xx status remains retryable transient

- **WHEN** `classify_upstream_failure` is called with `error_code="overloaded_error"` and `http_status` is 500, 502, 503, or 504
- **THEN** the returned `failure_class` is `retryable_transient`
- **AND** the result is the same as the no-status path, so the 5xx fallback heuristic is not the only signal driving the decision

#### Scenario: `server_is_overloaded` without a 5xx status is retryable transient

- **WHEN** `classify_upstream_failure` is called with `error_code="server_is_overloaded"` and `http_status` not in the 5xx range (including `None`)
- **THEN** the returned `failure_class` is `retryable_transient`
- **AND** the streaming retry layer is eligible to retry the request before surfacing the terminal overload event

#### Scenario: HTTP bridge retries a pre-created overload event

- **GIVEN** the HTTP responses session bridge is enabled
- **WHEN** the first upstream `response.failed` or `error` event has `code="overloaded_error"` or `code="server_is_overloaded"`
- **THEN** the bridge MUST retry the pre-created request before forwarding that terminal event
- **AND** the bridge MUST preserve its existing no-replay behavior after downstream-visible output or for other fail-fast error codes

### Requirement: Strict function tool parameter schemas are pre-validated

The service MUST pre-validate the JSON schema attached to a function tool when that tool sets `strict: true`, before opening any upstream connection. The validation rules mirror OpenAI's Structured Outputs strict-mode policy (https://platform.openai.com/docs/guides/structured-outputs) and the existing `enforce_strict_text_format` policy for `text.format.json_schema`:

- Every `object` schema node MUST set `additionalProperties: false`.
- Every property under `properties` MUST appear in `required`.
- Every schema node MUST carry a `type` key (no empty `{}` schemas).
- The same rules apply recursively to nested object / array / combinator (`anyOf` / `oneOf` / `allOf`) schemas.

When any of those rules is violated, the service MUST reject the request with `HTTP 400 invalid_request_error` carrying:

- `error.code = "invalid_function_parameters"`
- `error.message = "Invalid schema for function '<name>': In context=<path>, <reason>."`
- `error.param = "tools[<index>].parameters"` for native Responses-API requests; `error.param = "tools[<index>].function.parameters"` for chat-completions requests routed through the coercion pipeline.

This brings strict function tool schema handling into parity with `text.format.json_schema`. Without it, an invalid strict tool schema reaches the upstream Codex backend, which closes the WebSocket with `close_code=1000` and surfaces as a generic `502 server_error / upstream_rejected_input`. Real OpenAI returns `400 invalid_function_parameters` for the identical payload. A 5xx on a deterministically-broken request also triggers retry / failover loops in well-behaved clients.

#### Scenario: Strict tool missing `additionalProperties` is rejected with 400

- **WHEN** a client sends `tools: [{"type": "function", "name": "f", "parameters": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}, "strict": true}]`
- **THEN** the proxy returns `HTTP 400` with `error.code = "invalid_function_parameters"`, `error.message` matching `/Invalid schema for function 'f': In context=\(\), 'additionalProperties' is required to be supplied and to be false\./`, and `error.param = "tools[0].parameters"`

#### Scenario: Strict tool with `additionalProperties: true` is rejected

- **WHEN** a client sends a function tool with `strict: true` and `parameters.additionalProperties = true`
- **THEN** the proxy returns `HTTP 400 invalid_function_parameters` with the same `'additionalProperties' is required to be supplied and to be false` message

#### Scenario: Strict tool with property missing from `required` is rejected

- **WHEN** a client sends a function tool with `strict: true`, `additionalProperties: false`, but `required` omits one of the listed `properties`
- **THEN** the proxy returns `HTTP 400 invalid_function_parameters` with the `'required' is required to be supplied and to be an array including every key in properties` message

#### Scenario: Compliant strict tool is accepted

- **WHEN** a client sends a function tool with `strict: true`, `additionalProperties: false`, and every property listed in `required`
- **THEN** the proxy forwards the request to the upstream unchanged and the response is `200`

#### Scenario: `strict: false` or omitted strict skips pre-validation

- **WHEN** a client sends a function tool with `strict: false` or without a `strict` key, and the schema would have violated strict mode (e.g. missing `additionalProperties`)
- **THEN** the proxy does not run the strict pre-validation and forwards the request unchanged, matching pre-fix behavior for non-strict tools

### Requirement: Same-response side-effect tool-call replays are suppressed

When the proxy receives multiple downstream `response.output_item.done` events for the same response that describe the same side-effecting local tool operation, the proxy SHALL forward only the first event to the client.

The proxy SHALL treat `exec_command`, `write_stdin`, `multi_tool_use.parallel`, and `apply_patch_call` events as side-effecting. For these tools, a changed `call_id` alone MUST NOT make a same-response replay distinct.

When a `multi_tool_use.parallel` event contains duplicate nested side-effect operations, the proxy SHALL remove the duplicate nested operations before forwarding the event. Duplicate nested `exec_command` operations MUST ignore volatile output/wait fields such as `yield_time_ms` and `max_output_tokens`. Duplicate nested `write_stdin` operations MUST be scoped by `session_id` and `chars`. Duplicate nested `wait_agent` operations MUST be scoped by the target set.

Read-only function calls and matching operations under different response ids MUST continue to pass through.

#### Scenario: side-effect call replay uses a new call id

- **WHEN** a streamed response emits two `exec_command` output items with the same response id and arguments but different call ids
- **THEN** the proxy forwards the first event
- **AND** suppresses the second event

#### Scenario: read-only call ids stay distinct

- **WHEN** a streamed response emits two read-only function calls with the same arguments and different call ids
- **THEN** the proxy forwards both events

#### Scenario: later response ids stay distinct

- **WHEN** two responses emit the same side-effecting operation under different response ids
- **THEN** the proxy forwards both events

#### Scenario: parallel batch contains duplicate shell operations

- **WHEN** a `multi_tool_use.parallel` event contains two nested `functions.exec_command` operations with the same command and only different wait/output fields
- **THEN** the proxy forwards one nested operation inside the parallel batch
- **AND** does not forward the duplicate nested operation to the client

### Requirement: Continuity-dependent Responses follow-ups fail closed with retryable errors
When a Responses follow-up depends on previously established continuity state, the service MUST return a retryable continuity error if that continuity cannot be reconstructed safely. The service MUST NOT expose raw `previous_response_not_found` for bridge-local metadata loss or similar internal continuity gaps.

#### Scenario: HTTP bridge loses local continuity metadata for a follow-up request
- **WHEN** an HTTP `/v1/responses` or `/backend-api/codex/responses` follow-up request depends on `previous_response_id` or a hard continuity turn-state
- **AND** the bridge cannot reconstruct the matching live continuity state from local or durable metadata
- **THEN** the service returns a retryable OpenAI-format error
- **AND** the error code is not `previous_response_not_found`

#### Scenario: in-flight bridge follower loses continuity while waiting on the same canonical session
- **WHEN** a follow-up request waits on an in-flight HTTP bridge session for the same hard continuity key
- **AND** the bridge still cannot reconstruct safe continuity state once the leader finishes
- **THEN** the service returns a retryable OpenAI-format error
- **AND** the error code is not `previous_response_not_found`

#### Scenario: multiplexed follow-ups fail closed only for the matching continuity anchor
- **WHEN** a websocket or HTTP bridge session has multiple pending follow-up requests with different `previous_response_id` anchors
- **AND** continuity loss is detected for exactly one of those anchors
- **THEN** the service applies the retryable fail-closed continuity error only to the matching follow-up request
- **AND** it does not expose raw `previous_response_not_found`
- **AND** unrelated pending requests continue on their own response lifecycle

#### Scenario: multiplexed follow-ups sharing one anchor fail closed together without leaking raw continuity errors
- **WHEN** a websocket or HTTP bridge session has multiple pending follow-up requests that share the same `previous_response_id` anchor
- **AND** upstream emits an anonymous continuity loss event such as `previous_response_not_found` for that shared anchor
- **THEN** the service rewrites each affected follow-up into a retryable continuity error
- **AND** no affected follow-up exposes raw `previous_response_not_found`
- **AND** the run remains usable for subsequent requests after the rewritten failures

#### Scenario: single pre-created follow-up still fails closed when continuity loss omits explicit response id in message
- **WHEN** a websocket follow-up request is pending with `previous_response_id` and has not received a stable upstream `response.id` yet
- **AND** upstream emits `previous_response_not_found` with `param=previous_response_id`
- **AND** the upstream error message omits the literal previous response identifier
- **THEN** the service still maps that continuity loss to the pending follow-up
- **AND** it rewrites the downstream terminal event to a retryable continuity error
- **AND** it does not surface raw `previous_response_not_found` to the client

### Requirement: Hard continuity owner lookup fails closed
When a request depends on hard continuity ownership, the service MUST fail closed if owner or ring lookup errors prevent safe pinning. The service MUST NOT continue with local recovery or account selection that bypasses hard owner enforcement.

#### Scenario: websocket previous-response owner lookup errors
- **WHEN** a websocket or HTTP fallback follow-up request includes `previous_response_id`
- **AND** owner lookup errors prevent the proxy from determining the required owner account
- **THEN** the service returns a retryable OpenAI-format error
- **AND** it does not continue the request on an unpinned account

#### Scenario: bridge owner or ring lookup errors for hard continuity keys
- **WHEN** an HTTP bridge request uses a hard continuity key such as turn-state, explicit session affinity, or `previous_response_id`
- **AND** owner or ring lookup errors prevent the proxy from proving the correct bridge owner
- **THEN** the service returns a retryable OpenAI-format error
- **AND** it does not create or recover a local bridge session on the current replica

### Requirement: Request logs persist requested, actual, and billable service tiers separately
For Responses proxy traffic, the system MUST persist the operator-requested tier, the upstream-reported actual tier when available, and the effective billable tier used for pricing as separate request-log fields.

The legacy `fast` alias MUST be normalized to the canonical upstream value
`priority` before forwarding and before it is stored as the requested tier.
The upstream-reported `response.service_tier`, when present, remains the
authoritative actual tier even when it differs from the requested tier.

#### Scenario: Upstream reports a downgraded actual tier
- **WHEN** a client sends a Responses request with `service_tier: "priority"`
- **AND** the upstream response later reports `service_tier: "default"`
- **THEN** the persisted request log entry records `requested_service_tier = "priority"`
- **AND** the persisted request log entry records `actual_service_tier = "default"`
- **AND** the persisted request log entry records billable `service_tier = "default"`

#### Scenario: Fast alias is logged as a priority request
- **WHEN** a client sends a Responses request with `service_tier: "fast"`
- **AND** the upstream response later reports `service_tier: "default"`
- **THEN** the persisted request log entry records `requested_service_tier = "priority"`
- **AND** the persisted request log entry records `actual_service_tier = "default"`
- **AND** the persisted request log entry records billable `service_tier = "default"`

#### Scenario: Upstream omits the actual tier
- **WHEN** a client sends a Responses request with `service_tier: "priority"`
- **AND** the upstream response omits `service_tier`
- **THEN** the persisted request log entry records `requested_service_tier = "priority"`
- **AND** the persisted request log entry records `actual_service_tier = null`
- **AND** the persisted request log entry records billable `service_tier = "priority"`

### Requirement: API key service tier enforcement applies to upstream Responses requests

When an API key carries an enforced service tier, the proxy MUST override any incoming Responses request service tier with that enforced value before forwarding upstream. The legacy alias `fast` MUST be treated as `priority`.

#### Scenario: Enforced service tier overrides the request payload

- **WHEN** an API key is configured with `enforcedServiceTier: "priority"`
- **AND** an incoming Responses request asks for `service_tier: "default"`
- **THEN** the forwarded upstream payload uses `service_tier: "priority"`

#### Scenario: Fast alias is applied as priority

- **WHEN** an API key is configured with `enforcedServiceTier: "fast"`
- **THEN** the forwarded upstream payload uses the canonical value `priority`

### Requirement: Cursor GPT-5 model aliases normalize to canonical slugs

For Responses proxy traffic, the service MUST recognize Cursor-style GPT-5 model aliases formed by appending known suffix tokens
(`minimal`, `low`, `medium`, `high`, `xhigh`, `extra`, `fast`, `priority`, `reasoning`, `thinking`) to supported GPT-5 family slugs. The alias
resolver MUST match longer qualified canonical slugs before shorter family prefixes so aliases such as `gpt-5.4-mini-high` and `gpt-5.3-codex-fast` normalize
to the intended model. Unknown suffix tokens MUST leave the requested model unchanged.

#### Scenario: Qualified mini model alias normalizes reasoning

- **WHEN** a client sends a Responses request with `model: "gpt-5.4-mini-high"`
- **THEN** the forwarded upstream request uses `model: "gpt-5.4-mini"`
- **AND** the forwarded upstream request uses `reasoning.effort: "high"`

#### Scenario: Qualified codex model alias normalizes service tier

- **WHEN** a client sends a Responses request with `model: "gpt-5.3-codex-fast"`
- **THEN** the forwarded upstream request uses `model: "gpt-5.3-codex"`
- **AND** the forwarded upstream request uses `service_tier: "priority"`

### Requirement: OpenAI-compatible Responses payload sanitation removes provider-specific thinking aliases

The shared OpenAI-compatible Responses sanitation path MUST normalize third-party thinking aliases into the canonical `reasoning` object before upstream forwarding. Unknown provider-specific thinking controls MUST NOT be passed through unchanged to the upstream ChatGPT backend.

#### Scenario: Shared payload sanitation maps enable_thinking

- **WHEN** an internal Responses payload contains `enable_thinking: true`
- **AND** no explicit `reasoning.effort` is already present
- **THEN** the forwarded upstream payload includes `reasoning.effort: "medium"`
- **AND** the forwarded upstream payload does not include `enable_thinking`

#### Scenario: Explicit reasoning wins over provider aliases

- **WHEN** an internal Responses payload contains both `reasoning: {"effort":"high"}` and `thinking: {"type":"enabled"}`
- **THEN** the forwarded upstream payload keeps `reasoning.effort: "high"`
- **AND** the forwarded upstream payload does not include `thinking`

### Requirement: Public Responses streams expose renderable final text
For OpenAI-style streaming `/v1/responses` and `/backend-api/codex/responses`, the service MUST expose renderable `response.output_text.delta` events for assistant message text when upstream provides final text only in output item or terminal response output payloads. The service MUST NOT duplicate text deltas for an output item that already emitted a text delta.

#### Scenario: final output item text is exposed as a text delta
- **WHEN** upstream emits a `response.output_item.done` event with assistant message text and no prior text delta for that output item
- **THEN** the service emits a corresponding `response.output_text.delta` event before forwarding the final item event

#### Scenario: terminal response output text is exposed as a text delta
- **WHEN** upstream emits only a terminal `response.completed` event with assistant message text in `response.output`
- **THEN** the service emits a corresponding `response.output_text.delta` event before forwarding the terminal event

#### Scenario: existing text deltas are preserved without duplication
- **WHEN** upstream already emits a `response.output_text.delta` for an output item
- **THEN** the service forwards the stream without synthesizing another text delta for that same output item

### Requirement: Tool call events and output items are preserved
If the upstream model emits tool call deltas or output items, the service MUST forward those events in streaming mode and MUST include tool call items in the final response output for non-streaming mode.

#### Scenario: Tool call emitted
- **WHEN** the upstream emits a tool call delta event
- **THEN** the service forwards the delta event and includes the finalized tool call in the completed response output

#### Scenario: Chat Completions tool arguments avoid snapshot duplication
- **WHEN** `/v1/chat/completions` maps Responses tool-call events that include incremental deltas and later finalized snapshots for the same tool call
- **THEN** the final `tool_calls[].function.arguments` value is exactly one valid JSON string for that tool call
- **AND** the adapter MUST NOT append full snapshot payloads on top of already-collected incremental argument deltas

#### Scenario: Parallel tool calls route arguments by output_index
- **WHEN** `/v1/chat/completions` maps Responses events for two or more parallel function calls
- **THEN** the adapter MUST route each event to its `tool_calls[]` slot using the event's `output_index` as the primary routing key
- **AND** the adapter MUST preserve a stable mapping from `output_index` to the same slot across `output_item.added`, `output_item.done`, `response.function_call_arguments.delta`, and `response.function_call_arguments.done` events for that call
- **AND** parallel tool calls MUST NOT collapse to index `0` when their argument-only events identify the owning call only via `item_id`

#### Scenario: Parallel tool calls also resolve through item_id aliases
- **WHEN** an `output_item.added` or `output_item.done` event exposes both `item.id` (e.g. `"fc_..."`) and `item.call_id` (e.g. `"call_..."`)
- **THEN** the adapter MUST register `item.id` as an alias to the same `tool_calls[]` slot as the `call_id`
- **AND** subsequent argument-only events that carry only `item_id` MUST resolve to that aliased slot, even if their `output_index` has not yet been observed

#### Scenario: Internal item_id never leaks into the public call identifier
- **WHEN** the adapter exposes a tool call to the client as `tool_calls[].id` or `tool_calls[].call_id`
- **THEN** the value MUST be the upstream `call_...` identifier and MUST NOT be substituted with the internal `fc_...` item id used solely for routing

### Requirement: Responses routing prefers budget-safe accounts
When serving Responses routes, the service MUST prefer eligible accounts that are still below the configured budget threshold over eligible accounts already above that threshold. If no below-threshold candidate exists, the service MAY fall back to the pressured candidates.

#### Scenario: Fresh Responses request avoids a near-exhausted account
- **WHEN** `/backend-api/codex/responses`, `/backend-api/codex/responses/compact`, `/v1/responses`, or `/v1/responses/compact` selects among multiple eligible active accounts
- **AND** one candidate is above the configured budget threshold
- **AND** another candidate remains below that threshold
- **THEN** the below-threshold candidate is chosen first

### Requirement: Upstream Responses event size budget
The service SHALL allow upstream Responses SSE events and upstream websocket message frames up to 16 MiB by default before treating them as oversized.

#### Scenario: built-in tool output exceeds the old 2 MiB limit
- **WHEN** upstream Responses traffic includes a single SSE event or websocket message frame larger than 2 MiB but not larger than 16 MiB
- **THEN** the proxy continues processing the event instead of closing the upstream websocket locally with `1009 message too big`

### Requirement: Upstream Responses transport strategy
For streaming Codex/Responses proxy requests, the system MUST let operators choose the upstream transport strategy through dashboard settings. The resolved strategy MAY be `auto`, `http`, or `websocket`, and `default` MUST defer to the server configuration default.

#### Scenario: Dashboard forces websocket upstream transport
- **WHEN** the dashboard setting `upstream_stream_transport` is set to `"websocket"`
- **THEN** streaming Responses requests use the upstream websocket transport

#### Scenario: Dashboard forces HTTP upstream transport
- **WHEN** the dashboard setting `upstream_stream_transport` is set to `"http"`
- **THEN** streaming Responses requests use the upstream HTTP/SSE transport

#### Scenario: Auto transport falls back when websocket upgrades are rejected
- **WHEN** the resolved upstream transport strategy is `"auto"`
- **AND** auto selection chose the websocket transport
- **AND** the upstream rejects the websocket upgrade with HTTP `426`
- **THEN** the proxy retries the request over the upstream HTTP/SSE transport

#### Scenario: Session affinity alone does not trigger websocket upstream transport
- **WHEN** the resolved upstream transport strategy is `"auto"`
- **AND** a request includes a `session_id`
- **AND** it does not include an allowlisted native Codex `originator` or explicit Codex websocket feature headers
- **THEN** the auto strategy MUST keep using the existing model-preference transport selection rules

#### Scenario: Auto transport honors websocket-preferred bootstrap models before registry warmup
- **WHEN** the resolved upstream transport strategy is `"auto"`
- **AND** the model registry has not loaded a snapshot yet
- **AND** the request targets a locally bootstrapped websocket-preferred model family such as `gpt-5.4` or `gpt-5.4-*`
- **AND** the request does not include the built-in `image_generation` tool
- **THEN** the proxy chooses the upstream websocket transport

#### Scenario: Auto transport prefers HTTP for image-generation tool requests
- **WHEN** the resolved upstream transport strategy is `"auto"`
- **AND** the request includes a built-in `image_generation` tool
- **THEN** the proxy chooses the upstream HTTP/SSE transport even if the model would otherwise prefer websocket

#### Scenario: Legacy settings preserve the pre-feature default
- **WHEN** transport selection runs against a legacy settings object that does not expose the newer upstream transport fields
- **THEN** the proxy MUST preserve the pre-feature HTTP transport default for model-preference auto-selection unless an explicit legacy websocket mode or native Codex websocket signal opts in

### Requirement: Responses-compatible tool payload handling
The service SHALL accept built-in Responses tool definitions on `/backend-api/codex/responses` and `/v1/responses` without locally rejecting them. The service MAY normalize documented aliases, but upstream model/tool compatibility validation MUST remain the upstream contract.

#### Scenario: full Responses request includes built-in tools
- **WHEN** a client sends `/backend-api/codex/responses` or `/v1/responses` with built-in Responses tools such as `image_generation`, `computer_use`, `computer_use_preview`, `file_search`, or `code_interpreter`
- **THEN** the proxy forwards those tool objects upstream instead of returning a local `invalid_request_error`

### Requirement: Compact requests drop tool-only fields
The service SHALL remove `tools` and `tool_choice` from compact request payloads, and set `parallel_tool_calls` to `false`, before calling the upstream compact endpoint.

#### Scenario: compact request reuses a full Responses payload shape
- **WHEN** a client sends `/backend-api/codex/responses/compact` or `/v1/responses/compact` with `tools`, `tool_choice`, or `parallel_tool_calls`
- **THEN** the proxy drops `tools` and `tool_choice` before the upstream compact request
- **AND** the proxy sends `parallel_tool_calls` as `false`
- **AND** the compact request continues without a local or upstream `invalid_request_error` caused by `param="tools"`

### Requirement: Responses requests accept input_file content items with a file_id

The system SHALL accept `input_file` content items that reference an upload by `file_id` in `/backend-api/codex/responses` and `/v1/responses` request payloads (both list-form and string-form `input`). These items MUST be forwarded to upstream verbatim. The same MUST apply to `/responses/compact` request bodies. The proxy MUST NOT raise `input_file.file_id is not supported` for these items.

#### Scenario: input_file with file_id is accepted in a /responses request

- **WHEN** a client posts a `/v1/responses` request whose `input` contains a `{"type": "input_file", "file_id": "file_abc"}` content item
- **THEN** the request validates and the upstream payload includes that content item unchanged

#### Scenario: input_file with file_id is accepted in a compact request

- **WHEN** a client posts a `/responses/compact` request whose `input` contains an `input_file` item with a `file_id`
- **THEN** the request validates and is forwarded to upstream verbatim

### Requirement: Responses requests with input_file.file_id route to the upload's account

A `/v1/responses`, `/backend-api/codex/responses`, or `/responses/compact` request that references an `{type: "input_file", file_id}` content item SHALL be routed to the upstream account that registered the file via `POST /backend-api/files`, when an in-memory pin for that `file_id` is still live. Stronger affinity signals MUST take precedence over the file_id pin: an explicit `prompt_cache_key`, a session header (`StickySessionKind.CODEX_SESSION`), a turn-state header, or a `previous_response_id` MUST keep their existing routing semantics.

When multiple `file_id`s are referenced and several are pinned, the most-recently-pinned one MUST be preferred (with a deterministic lexicographic tie-break on `file_id`).

#### Scenario: file_id pin drives routing for an input_file response

- **GIVEN** a `POST /backend-api/files` registered `file_xyz` through `account_a`
- **WHEN** a `/v1/responses` request references `{"type": "input_file", "file_id": "file_xyz"}` and has no stronger affinity
- **THEN** the proxy MUST route the request to `account_a`

#### Scenario: prompt_cache_key overrides the file_id pin

- **GIVEN** a pinned `file_xyz -> account_a`
- **WHEN** a `/v1/responses` request references `file_xyz` AND sets an explicit `prompt_cache_key`
- **THEN** the proxy MUST follow the prompt-cache affinity for routing and MUST NOT use the file_id pin

### Requirement: Codex backend session_id preserves account affinity
When a backend Codex Responses or compact request includes a non-empty accepted session header, the service MUST use that value as the routing affinity key for upstream account selection. If the request lacks a client-supplied `prompt_cache_key`, the service MUST derive and attach a stable `prompt_cache_key` before upstream forwarding so account affinity and upstream prompt-cache routing can coexist. Accepted session headers are `session_id`, `x-codex-session-id`, and `x-codex-conversation-id`, in that priority order.

#### Scenario: Backend Codex request derives prompt_cache_key before codex-session routing
- **WHEN** `/backend-api/codex/responses` is called with `session_id` and without `prompt_cache_key`
- **THEN** the routing decision still uses durable `codex_session` affinity for account selection
- **AND** the forwarded upstream payload includes a derived stable `prompt_cache_key`

### Requirement: Proxy-generated prompt cache key derivation is operator-toggleable
The service MUST provide a runtime flag that disables only proxy-generated prompt-cache-key derivation. When disabled, the service MUST continue forwarding any client-supplied `prompt_cache_key` unchanged and MUST NOT synthesize a new one.

#### Scenario: Derivation disabled preserves client-supplied key
- **WHEN** the derivation flag is disabled and a client sends `prompt_cache_key`
- **THEN** the service forwards that key unchanged
- **AND** it does not generate a replacement key

### Requirement: HTTP Responses routes preserve upstream websocket session continuity
When serving HTTP `/v1/responses` or HTTP `/backend-api/codex/responses`, the service MUST preserve upstream Responses websocket session continuity on a stable per-session bridge key instead of opening a brand new upstream session for every eligible request. The bridge key MUST use an explicit session/conversation header when present; otherwise it MUST use normalized `prompt_cache_key`, and when the client omits `prompt_cache_key` the service MUST derive a stable key from the same cache-affinity inputs already used for OpenAI prompt-cache routing. While bridged, the service MUST preserve the external HTTP/SSE contract, MUST continue request logging with `transport = "http"`, and MUST keep requests from different bridge keys isolated from one another.

#### Scenario: bridge forwards hard continuity keys to the owner replica
- **WHEN** operators configure multiple eligible bridge instance ids
- **AND** a request uses a bridge key derived from `x-codex-turn-state` or an explicit session header
- **AND** that request lands on a non-owner instance
- **THEN** the service MUST forward the request internally to the owner replica
- **AND** it MUST NOT return a topology-bearing `bridge_instance_mismatch` error to the client for that owner mismatch alone

#### Scenario: gateway-style prompt-cache bridge requests tolerate wrong-replica arrival
- **WHEN** a request uses a bridge key derived only from `prompt_cache_key` or a derived prompt-cache key
- **AND** that request lands on a non-owner instance
- **THEN** the service MAY create or reuse a local bridge session on that instance
- **AND** it MUST treat the owner mismatch as a locality miss instead of a continuity failure

#### Scenario: forwarded bridge requests fail closed when owner forwarding loops
- **WHEN** a forwarded hard-continuity bridge request reaches another non-owner replica
- **THEN** the service MUST fail the request with a generic 5xx bridge-forward error
- **AND** it MUST NOT attempt another owner handoff

#### Scenario: local restart orphan is recovered by the replacement instance
- **WHEN** a single local bridge instance is replaced while durable hard-continuity ownership still references the old instance id
- **AND** the old owner has no distinct active forwarding endpoint from the current replacement instance
- **THEN** the replacement instance MUST treat the row as restart-orphaned and may claim durable ownership locally
- **AND** same-account takeover MUST preserve the latest persisted response anchor until a replacement response id is recorded
- **AND** normal client retries MUST NOT be stranded waiting for the old instance lease to expire

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

### Requirement: Responses account selection accounts for in-flight pressure

For Responses API requests, usage-based routing MUST include immediate in-process account pressure in addition to persisted usage. Account selection MUST account for in-flight response-create work, active streams, leased token/cost estimates, recent selection pressure, account health, and configured account-local caps. Selection and lease acquisition MUST be atomic with respect to other in-process selections, and the critical section MUST NOT perform database calls, network calls, sleeps, or other blocking I/O.

#### Scenario: Concurrent burst spreads before upstream usage refreshes

- **GIVEN** multiple eligible accounts have similar persisted usage
- **WHEN** many `/v1/responses` requests arrive concurrently before upstream usage refreshes
- **THEN** selected accounts are distributed according to immediate in-flight pressure and caps
- **AND** one account does not receive all requests solely because persisted usage was stale

#### Scenario: File-pinned bridge request does not reroute under local pressure

- **GIVEN** an HTTP bridge `/v1/responses` request references an `input_file.file_id` pinned to an upstream account
- **AND** that owner account or bridge session rejects admission with local pressure before output starts
- **WHEN** the proxy handles the admission failure
- **THEN** it returns the owner account overload instead of soft-rerouting the payload to another account
- **AND** the file-scoped request is not replayed to an account that does not own the file

#### Scenario: Runtime lock excludes blocking I/O

- **WHEN** account selection holds the balancer runtime lock
- **THEN** the implementation performs only in-memory scoring and lease mutation
- **AND** database, network, sleep, or bridge queue waits happen outside that lock

### Requirement: Account leases release on all terminal paths

Every account-local lease acquired for a Responses request MUST be idempotently released or settled on success, upstream error, local startup error, bridge submit failure, startup probe conversion, non-streaming collect completion, failover, downstream disconnect, cancellation, timeout, retry, pending-request teardown, and request-to-connection ownership replacement. A bounded stale-lease watchdog MUST reclaim leases that survive unexpected task cancellation or exceptions, and stale reclamation MUST emit warning/metric evidence. Leases MUST NOT be persisted to the database.

#### Scenario: Lease releases after downstream disconnect

- **WHEN** a streaming `/v1/responses` client disconnects before a terminal upstream event
- **THEN** the account stream lease is released exactly once
- **AND** later routing pressure no longer includes that stream

#### Scenario: WebSocket local account cap releases API-key reservation

- **GIVEN** a WebSocket `response.create` has reserved API-key usage
- **AND** account-local response-create lease acquisition fails with `account_response_create_cap`
- **WHEN** the proxy emits the local terminal failure
- **THEN** the API-key usage reservation is released
- **AND** the pending request is removed from websocket local state

#### Scenario: Stale watchdog recovers orphaned lease

- **WHEN** a request task exits unexpectedly after acquiring an account lease
- **AND** the lease exceeds the configured TTL
- **THEN** the watchdog releases the stale lease
- **AND** emits a low-cardinality warning/metric

#### Scenario: Active stream lease is not reclaimed before valid stream budget

- **GIVEN** a stream lease is older than the base lease TTL
- **AND** the configured Responses stream or HTTP bridge request budget has not elapsed
- **WHEN** account lease stale reclamation runs
- **THEN** the stream lease still counts against account-local stream pressure
- **AND** the proxy does not admit extra streams over the account stream cap by age alone

#### Scenario: Replacing the active WebSocket request releases the previous stream lease

- **GIVEN** a WebSocket connection holds an account stream lease for its active upstream reader
- **AND** the next pending `response.create` owns a reserved account stream lease
- **WHEN** the connection adopts the pending request's lease
- **THEN** the previous connection-owned lease is released before the local lease reference is replaced
- **AND** the adopted lease is removed from pending request state so exactly one owner remains

#### Scenario: Pending WebSocket teardown releases an untransferred stream lease

- **GIVEN** a pending WebSocket request owns a reserved account stream lease that has not transferred to the connection
- **WHEN** disconnect or teardown fails and removes that pending request
- **THEN** the request-owned stream lease is released and cleared exactly once
- **AND** later routing pressure no longer includes that stream

### Requirement: Public Responses streaming is proxy-timeout friendly

Streaming `/v1/responses` responses MUST include anti-buffering/cache headers suitable for SSE through common front-door proxies and MUST emit an early flushable SSE comment or event before long upstream startup waits can appear idle. Periodic SSE keepalive behavior MUST continue while waiting for upstream events. These heartbeat comments MUST NOT violate the public Responses event contract: OpenAI-contract events still begin with `response.created` when event parsing ignores comments.

#### Scenario: Streaming response includes anti-buffering headers

- **WHEN** a client starts streaming `POST /v1/responses`
- **THEN** the response headers include SSE content type and anti-buffering/cache directives
- **AND** the headers are present before upstream response completion

#### Scenario: Early heartbeat precedes long upstream silence

- **WHEN** upstream startup takes longer than the heartbeat interval
- **THEN** the client receives a flushable SSE heartbeat before a front-door origin idle timeout would trigger
- **AND** the first OpenAI-contract event remains `response.created` when upstream accepts the request

### Requirement: Codex WebSocket top-level previous-response errors are masked
When serving the Codex-native `/backend-api/codex/responses` WebSocket route, the proxy MUST treat upstream `type: "error"` frames with top-level error fields as upstream error envelopes if the frame does not contain a nested `error` object. If those fields describe a `previous_response_not_found` continuity miss, the proxy MUST use the existing continuity fail-closed behavior and MUST NOT forward raw `previous_response_not_found` or the missing response id to the downstream Codex client.

#### Scenario: ChatGPT backend emits top-level previous-response miss on Codex websocket
- **WHEN** a `/backend-api/codex/responses` WebSocket follow-up has `previous_response_id`
- **AND** the ChatGPT backend emits `{"type":"error","code":"previous_response_not_found","param":"previous_response_id",...}` without a nested `error` object
- **THEN** the downstream event is a retryable continuity failure such as `stream_incomplete`
- **AND** the downstream payload does not contain `previous_response_not_found`
- **AND** the downstream payload does not expose the missing previous response id

### Requirement: Equal idle and request-budget stream deadlines preserve idle classification
When the configured upstream stream idle timeout is equal to the proxy request budget, and an already-started streaming Responses body has had no upstream activity for the full shared window, the system MUST classify the timeout as `stream_idle_timeout` even if scheduler jitter observes the deadline after it has elapsed. When the request budget is strictly shorter than the stream idle timeout, when the generic total timeout fires before an upstream response has started, when the remaining request budget for the next read is shorter than a fresh idle window, or when a generic total timeout follows recent upstream body activity, the system MUST continue to classify the timeout as `upstream_request_timeout`.

#### Scenario: Direct HTTP stream body deadline tie is classified as idle
- **GIVEN** `stream_idle_timeout_seconds` equals `proxy_request_budget_seconds`
- **AND** the upstream HTTP response headers have been received
- **WHEN** reading the response body times out just after that shared deadline
- **THEN** the downstream failure event uses `error.code = "stream_idle_timeout"`
- **AND** the error message is `"Upstream stream idle timeout"`

#### Scenario: Pre-response total timeout remains request-timeout classified
- **GIVEN** `stream_idle_timeout_seconds` equals `proxy_request_budget_seconds`
- **WHEN** the generic request total timeout fires before an upstream response has started
- **THEN** the downstream failure event uses `error.code = "upstream_request_timeout"`
- **AND** the error message is `"Proxy request budget exhausted"`

#### Scenario: Direct HTTP total timeout after recent activity remains request-timeout classified
- **GIVEN** `stream_idle_timeout_seconds` equals `proxy_request_budget_seconds`
- **AND** an upstream HTTP response body chunk was received less than a full idle window ago
- **WHEN** the generic request total timeout fires at the request-budget deadline
- **THEN** the downstream failure event uses `error.code = "upstream_request_timeout"`
- **AND** the error message is `"Proxy request budget exhausted"`

#### Scenario: Shorter request budget remains request-timeout classified
- **GIVEN** `proxy_request_budget_seconds` is strictly shorter than `stream_idle_timeout_seconds`
- **WHEN** the request budget elapses before the idle timeout
- **THEN** the downstream failure event uses `error.code = "upstream_request_timeout"`
- **AND** the error message is `"Proxy request budget exhausted"`

#### Scenario: Owner-forward receive deadline tie is classified as idle
- **GIVEN** an HTTP bridge owner-forward stream has equal idle and request-budget deadlines
- **AND** the remaining request budget for the next read is at least a full idle window
- **WHEN** receiving the next upstream chunk times out at that shared deadline
- **THEN** the owner-forward timeout uses `error_code = "stream_idle_timeout"`

#### Scenario: Owner-forward shorter remaining budget is request-timeout classified
- **GIVEN** an HTTP bridge owner-forward stream has equal configured idle and request-budget deadlines
- **AND** the remaining request budget for the next read is shorter than a fresh idle window
- **WHEN** receiving the next upstream chunk times out at the request-budget deadline
- **THEN** the owner-forward timeout uses `error_code = "upstream_request_timeout"`

### Requirement: Multiplexed websocket timeout ties preserve younger pending requests
When an upstream websocket or HTTP bridge session has multiple pending Responses turns and the oldest pending turn reaches an equal idle/request-budget deadline, the system MUST NOT fail all pending turns solely because the equal deadline is classified as `stream_idle_timeout`. It MUST fail only pending turns whose own request budget has elapsed, and it MUST keep younger pending turns queued until their own terminal event or timeout.

#### Scenario: Equal deadline on oldest pending request does not fail younger sibling
- **GIVEN** two pending websocket Responses requests share an upstream session
- **AND** the oldest request has reached an equal idle/request-budget deadline
- **AND** the younger request still has request budget remaining
- **WHEN** the upstream receive watchdog fires
- **THEN** the timeout classification is `stream_idle_timeout`
- **AND** the fail-all-pending path is not used
- **AND** only the expired oldest request is failed
- **AND** the younger request remains pending

### Requirement: HTTP bridge streams emit downstream liveness frames while pending

When an HTTP bridge Responses request is waiting for upstream queue events, the system MUST emit a downstream SSE liveness frame at the configured `sse_keepalive_interval_seconds` interval so downstream clients do not disconnect before the upstream terminal frame arrives. The first generated liveness frame MUST be delayed until after the HTTP bridge startup-error probe window so a local startup `ProxyResponseError` can still be surfaced as a non-2xx HTTP response. Once a generated liveness frame is emitted, the stream MUST be considered started for later HTTP-error propagation decisions, so a subsequent upstream `response.failed` is forwarded in-stream instead of being raised as a startup HTTP error.

If the pending request already has a response id, the liveness frame MAY be a `response.in_progress` SSE event for that response id. Before a response id exists, a verified native Codex client on `/backend-api/codex/responses` MUST receive an event-bearing `codex.keepalive` JSON SSE frame even when payload-shape heuristics also require OpenAI-compatible response normalization, because comment-only frames do not reset the native client's parsed-event idle timer. Native identity MUST come from the existing native User-Agent or originator allowlist and MUST NOT be inferred from continuity headers.

Explicit OpenAI SDK fingerprint markers, including `x-stainless-*` headers or an OpenAI User-Agent, MUST retain precedence for heartbeat framing and MUST receive comment liveness. Public `/v1/responses` and other non-native OpenAI SDK streams MUST retain comment heartbeats before `response.created`; public stream normalization MUST preserve those comments and MUST drop `codex.*` liveness events from the OpenAI contract surface. Heartbeat selection MUST NOT disable authentication, payload validation, event normalization, fingerprint normalization, or routing policy.

#### Scenario: Native Desktop shape receives parsed-event liveness

- **GIVEN** Codex Desktop sends `POST /backend-api/codex/responses` with a verified native User-Agent or originator
- **AND** its OpenAI-compatible payload and `Accept` header also trigger SDK-compatible event normalization
- **WHEN** no upstream event arrives before a response id is known
- **THEN** the proxy emits an event-bearing `codex.keepalive` JSON SSE frame
- **AND** it preserves any required response-event normalization

#### Scenario: Explicit SDK marker retains comment liveness

- **GIVEN** a request to `/backend-api/codex/responses` carries an `x-stainless-*` header or OpenAI User-Agent
- **WHEN** its payload also resembles a native Codex request
- **THEN** the proxy emits an SSE comment heartbeat before `response.created`
- **AND** it does not expose `codex.*` vendor events to the SDK stream

#### Scenario: Public v1 route never exposes native vendor heartbeat

- **GIVEN** a request targets public `/v1/responses`
- **WHEN** the request is pending before `response.created`
- **THEN** periodic liveness uses OpenAI-contract-safe comment frames
- **AND** the first data event remains `response.created`

#### Scenario: First HTTP bridge keepalive is delayed past startup probe

- **GIVEN** an HTTP bridge request is waiting for upstream queue events
- **AND** `sse_keepalive_interval_seconds` is shorter than the bridge startup-error probe window
- **WHEN** no upstream event arrives before the configured keepalive interval
- **THEN** the first generated keepalive is not emitted until the startup-error probe window has elapsed
- **AND** a startup `ProxyResponseError` can still be surfaced as a non-2xx HTTP response before any keepalive commits the stream

#### Scenario: HTTP bridge keepalive commits stream for later response-failed events

- **GIVEN** an HTTP bridge request emits a generated keepalive as its first downstream chunk
- **WHEN** the next upstream event is a `response.failed` with an HTTP status override
- **THEN** the `response.failed` event is forwarded on the SSE stream
- **AND** it is not raised as a startup HTTP error after bytes have already been emitted

#### Scenario: Public Responses normalizer preserves comment keepalive blocks

- **WHEN** the public `/v1/responses` stream normalizer receives an SSE comment keepalive block before a terminal event
- **THEN** it forwards the comment keepalive block unchanged
- **AND** it continues normalizing the subsequent Responses events normally

### Requirement: Codex WebSocket pre-created turns receive application heartbeats
When serving the Codex-native `/backend-api/codex/responses` WebSocket route, the proxy SHALL emit a parseable Codex vendor heartbeat while a `response.create` request is pending but upstream has not yet emitted `response.created`. The heartbeat MUST be an application text frame so Codex clients reset stream-idle watchdogs that do not observe WebSocket protocol ping/pong frames. Once upstream assigns a response id, the proxy MUST continue using the existing `response.in_progress` heartbeat shape for that response id.

#### Scenario: Codex websocket upstream is silent before response.created
- **GIVEN** a Codex-native WebSocket `/backend-api/codex/responses` request is pending
- **AND** upstream has not emitted `response.created` for the request
- **WHEN** no upstream application frame arrives before the configured keepalive interval
- **THEN** the proxy emits a `codex.keepalive` text event downstream
- **AND** the request remains pending for the upstream `response.created` or terminal event

#### Scenario: OpenAI-style v1 websocket does not receive Codex vendor heartbeat
- **GIVEN** an OpenAI-style WebSocket `/v1/responses` request is pending
- **AND** upstream has not emitted `response.created` for the request
- **WHEN** no upstream application frame arrives before the configured keepalive interval
- **THEN** the proxy MUST NOT emit a `codex.keepalive` vendor event downstream

### Requirement: WebSocket terminal auth failures recover before visible output

When a Codex or OpenAI-compatible Responses WebSocket request receives an upstream terminal `response.failed` or `error` before downstream-visible output with `error.code = "invalid_api_key"` or `error.type = "authentication_error"`, the proxy MUST treat the failure as account-local auth state instead of immediately surfacing the terminal event. The proxy MUST preserve the existing no-replay rule after downstream-visible output or for non-replayable continuation requests.

#### Scenario: Session-ended WebSocket auth failure uses another account

- **GIVEN** at least two accounts are eligible for a WebSocket `response.create` request
- **AND** the selected account returns a pre-visible terminal auth failure whose message says the session ended or asks the user to log in again
- **WHEN** another eligible account can complete the request
- **THEN** the downstream WebSocket response succeeds from the other account
- **AND** the selected account is marked re-authentication-required and excluded from that replay

#### Scenario: Generic WebSocket auth failure refreshes once before failover

- **GIVEN** at least two accounts are eligible for a WebSocket `response.create` request
- **AND** the selected account returns a pre-visible terminal `invalid_api_key` failure
- **WHEN** the forced-refresh replay on the selected account also returns a pre-visible terminal `invalid_api_key` failure
- **THEN** the proxy excludes the selected account and tries another eligible account
- **AND** the downstream WebSocket response succeeds from the other account when it completes

#### Scenario: WebSocket auth failure after visible output is not replayed

- **GIVEN** a WebSocket response has emitted downstream-visible output
- **WHEN** upstream later returns a terminal `invalid_api_key` or `authentication_error`
- **THEN** the proxy MUST surface the terminal error without replaying the request on another account

### Requirement: Compact auth failures fail over after forced refresh

The proxy MUST recover from account-local compact authentication failures before
surfacing them to the compact client. When a `/backend-api/codex/responses/compact`
request receives an upstream `401 invalid_api_key` response for the selected
account, the proxy MUST attempt one forced token refresh and retry the compact
request on that same account. If the refreshed retry also returns `401`, the
proxy MUST classify and record the account failure, exclude that account from
the current compact request, and try another eligible account when one is
available. The proxy MUST NOT surface the repeated account-local `401` to the
compact client before exhausting eligible accounts.

#### Scenario: Refreshed compact auth failure uses another account

- **GIVEN** at least two accounts are eligible for a compact request
- **AND** the selected account returns `401 invalid_api_key` for compact before and after a forced refresh
- **WHEN** another eligible account can complete the compact request
- **THEN** the downstream compact response succeeds from the second account
- **AND** the selected account is excluded from further attempts for that compact request

#### Scenario: Compact 401 is not a generic same-contract retry

- **WHEN** low-level compact transport receives HTTP 401 from upstream
- **THEN** the service-level auth refresh/failover path handles it
- **AND** the low-level compact transport does not mark it as a generic same-contract transport retry

### Requirement: Pre-visible proxy auth failures fail over after forced refresh

The proxy MUST treat repeated account-local authentication failures as
per-request account failures before any downstream-visible output is emitted.
When a proxy request on a non-compact surface retries with a refreshed token and
the refreshed retry still returns upstream `401 invalid_api_key`, the proxy MUST
classify and record the selected account failure, exclude that account from the
current request, and try another eligible account when one is available. The
proxy MUST preserve the existing no-replay rule after downstream-visible stream
or websocket output has been emitted.

#### Scenario: Pre-visible streaming auth failure uses another account

- **GIVEN** at least two accounts are eligible for a streaming responses request
- **AND** the selected account returns `401 invalid_api_key` before downstream-visible output
- **WHEN** another eligible account can complete the request
- **THEN** the downstream stream succeeds from another account
- **AND** the selected account is excluded from further attempts for that request

#### Scenario: Non-stream proxy auth failure uses another account

- **GIVEN** at least two accounts are eligible for a thread-goal, Codex control,
  transcription, or file create/finalize request
- **AND** the selected account returns `401 invalid_api_key` before and after a forced refresh
- **WHEN** another eligible account can complete the request
- **THEN** the downstream request succeeds from another account
- **AND** the selected account is excluded from further attempts for that request

#### Scenario: Websocket connect auth failure uses another account

- **GIVEN** at least two accounts are eligible for an upstream websocket connect
- **AND** the selected account returns `401 invalid_api_key` after a forced refresh retry
- **WHEN** another eligible account can open the upstream websocket
- **THEN** the websocket connect path excludes the invalidated account and tries another account

#### Scenario: HTTP bridge handshake auth failure uses another account

- **GIVEN** at least two accounts are eligible for HTTP bridge session creation or reconnect
- **AND** the selected account returns `401 invalid_api_key` after a forced refresh retry
- **WHEN** another eligible account can open the upstream websocket handshake
- **THEN** the HTTP bridge path excludes the invalidated account and tries another account

### Requirement: Codex WebSocket wrapped errors follow official client shape

When serving `/backend-api/codex/responses` or bridge-backed Responses WebSocket traffic, the service MUST classify upstream `type: "error"` frames using the same wrapped-error shape that the official Codex client accepts: a non-2xx `status` or `status_code` field indicates an upstream HTTP-style error, and the error detail MAY appear either in a nested `error` object or in top-level fields such as `code`, `message`, `param`, and `error_type`.

Top-level error normalization MUST NOT treat the event discriminator `type: "error"` as the upstream error type. If the frame provides `error_type`, the service MUST use that value as the error type for classification/rewrites. Existing continuity protection remains authoritative: frames describing `previous_response_not_found` MUST be rewritten or recovered through the established `stream_incomplete` continuity path instead of exposing the raw upstream code or missing response id.

#### Scenario: status_code alias is classified as upstream error status

- **WHEN** an upstream Codex WebSocket frame is `{"type":"error","status_code":400,...}`
- **THEN** the service treats the HTTP-style error status as `400`
- **AND** applies the same error classification path as for `status: 400`

#### Scenario: top-level error_type is used for classification

- **WHEN** an upstream Codex WebSocket frame is `{"type":"error","status":400,"error_type":"invalid_request_error","code":"previous_response_not_found",...}`
- **THEN** the normalized error detail has `type = "invalid_request_error"`
- **AND** the event discriminator `type = "error"` is not used as the upstream error type

#### Scenario: top-level previous-response miss remains masked

- **WHEN** a `/backend-api/codex/responses` WebSocket follow-up has `previous_response_id`
- **AND** upstream emits a top-level `previous_response_not_found` wrapped-error frame using `status_code`
- **THEN** the downstream event is a retryable continuity failure such as `stream_incomplete`
- **AND** the downstream payload does not contain `previous_response_not_found`
- **AND** the downstream payload does not expose the missing previous response id

### Requirement: Backend Codex Responses preserve advertised image_generation tools
The service MUST accept HTTP and websocket `/backend-api/codex/responses`
request-create payloads that include top-level `tools` entries with
`type: "image_generation"`. During shared Responses validation and upstream
forwarding, the service MUST preserve those top-level `image_generation` tool
entries so Codex clients can expose and use the built-in image-generation
surface. The service MUST also preserve all other tool entries and the existing
built-in tool forwarding policy for public `/v1/*` routes.

#### Scenario: Backend Codex HTTP request preserves advertised image_generation tool
- **WHEN** a client sends `POST /backend-api/codex/responses` with
  `tools=[{"type":"image_generation"},{"type":"function","name":"x"}]`
- **THEN** the request is accepted instead of failing with
  `invalid_request_error`
- **AND** the upstream Responses payload preserves the `image_generation` tool
- **AND** the remaining `function` tool is preserved

#### Scenario: Backend Codex websocket create preserves advertised image_generation tool
- **WHEN** a websocket `response.create` payload for
  `/backend-api/codex/responses` includes a top-level
  `{"type":"image_generation"}` tool entry
- **THEN** the backend Codex websocket request is accepted
- **AND** the forwarded upstream `response.create` payload preserves that
  `image_generation` tool entry

#### Scenario: Public v1 Responses built-in forwarding policy remains unchanged
- **WHEN** a client sends `/v1/responses` with
  `tools=[{"type":"image_generation"}]`
- **THEN** the service does not locally reject the built-in tool as an
  `invalid_request_error`
- **AND** the upstream Responses payload preserves the `image_generation` tool

### Requirement: HTTP bridge startup waits fail with terminal local overload

When the HTTP responses bridge cannot start upstream work because its local bridge startup waits do not make progress within the configured proxy admission wait timeout, the service MUST surface a terminal local-overload error instead of leaving `/v1/responses`, `/backend-api/codex/responses`, or compact responses streams on keepalives only.

#### Scenario: HTTP bridge startup wait stalls before first upstream event

- **WHEN** a streaming Responses request enters the HTTP responses bridge
- **AND** bridge startup is blocked by local bridge admission state before any upstream `response.*` event can be emitted
- **AND** the wait exceeds the configured proxy admission wait timeout
- **THEN** the request fails with a terminal error
- **AND** the error payload identifies local proxy overload with `error.code = "proxy_overloaded"`

### Requirement: Accept duplicated /v1/ prefix under /backend-api/codex
The service MUST treat any inbound request whose path begins with `/backend-api/codex/v1/` followed by a non-empty rest as a transparent alias for the same path with the `/v1` segment removed. Some OpenAI-compatible clients append `/v1/` to whatever the operator configured as the base URL, producing paths like `/backend-api/codex/v1/models` or `/backend-api/codex/v1/responses`. The aliasing MUST be applied before routing so the canonical handler runs unchanged. The aliasing MUST NOT trigger for `/backend-api/codex/v1` or `/backend-api/codex` with no further path. The top-level OpenAI-style `/v1/<rest>` routes are unaffected.

#### Scenario: Misbehaving client requests duplicated prefix
- **WHEN** a client requests `GET /backend-api/codex/v1/models`
- **THEN** the response is identical to `GET /backend-api/codex/models`

#### Scenario: Canonical paths are unchanged
- **WHEN** a client requests `GET /backend-api/codex/models` or `GET /v1/models`
- **THEN** the request is routed to its existing handler without modification

### Requirement: Backend Responses endpoint accepts OpenAI-compatible request shapes
The `/backend-api/codex/responses` HTTP endpoint SHALL accept the OpenAI-compatible Responses request shape used by `/v1/responses`, including a plain string `input` and omitted or explicit `null` `instructions`. The endpoint MUST normalize that request into the internal Responses request model before forwarding upstream, MUST continue returning `text/event-stream` SSE Responses events, and MUST preserve Codex-specific session/cache affinity behavior for the backend route.

#### Scenario: OpenAI SDK streams through backend Responses path
- **WHEN** an OpenAI-compatible client sends `POST /backend-api/codex/responses` with `stream=true`, a model, and a plain string `input`
- **THEN** the proxy accepts the request without requiring `instructions`
- **AND** the response is a `text/event-stream` stream containing Responses events such as `response.output_text.delta` and `response.completed`

#### Scenario: Codex-private stream metadata is hidden from OpenAI SDK clients
- **WHEN** upstream emits a Codex-private stream event such as `codex.rate_limits` before `response.created`
- **THEN** the HTTP Responses stream omits the private event from the downstream SSE body
- **AND** OpenAI SDK clients can consume the stream without failing their Responses event ordering checks

#### Scenario: Strict function tool schemas are validated before streaming
- **WHEN** an OpenAI-compatible client sends `POST /backend-api/codex/responses` with a strict function tool schema that violates the supported JSON Schema subset
- **THEN** the proxy rejects the request with a deterministic 400 `invalid_function_parameters` error before opening the stream

#### Scenario: Codex-native backend Responses shape is preserved
- **WHEN** a Codex client sends `POST /backend-api/codex/responses` with `instructions`, array-shaped `input`, and Codex affinity headers
- **THEN** the proxy preserves the normalized request content and continues applying backend Codex session affinity

### Requirement: Codex WebSocket stale-anchor failures remain recoverable by a full-context retry
When serving or consuming the Codex-native `/backend-api/codex/responses` WebSocket route, upstream `previous_response_id` MUST be treated as an ephemeral optimization rather than durable conversation state. A stale-anchor continuity failure during a long-wait tool-output continuation MUST NOT hard-end the user turn before one full-context retry without `previous_response_id` has been attempted.

#### Scenario: Long-running terminal wait invalidates the upstream previous response anchor
- **GIVEN** a Codex-native WebSocket session has completed a response with id `resp_old`
- **AND** the client later sends a `response.create` frame with `previous_response_id: "resp_old"` and tool-output or other delta input after a long idle period
- **WHEN** the upstream rejects `resp_old` with a stale-anchor error such as `previous_response_not_found`
- **THEN** the failure is classified as stale-anchor continuity loss
- **AND** the client-side recovery path retries once using full conversation history without `previous_response_id` before surfacing a turn-ending error
- **AND** the downstream/user-visible error path does not expose raw `previous_response_not_found` or the missing upstream response id

#### Scenario: codex-lb sanitizes stale-anchor errors for client classification
- **WHEN** upstream emits a direct WebSocket stale-anchor error
- **THEN** codex-lb MUST NOT forward raw `previous_response_not_found`
- **AND** codex-lb MUST NOT expose the missing upstream response id downstream
- **AND** codex-lb MUST preserve a stable sanitized classifier that lets a compatible Codex client distinguish stale-anchor continuity loss from quota, policy, auth, and generic invalid-request failures

#### Scenario: Non-stale-anchor failures do not trigger full-context retry
- **WHEN** the upstream failure is quota, policy, auth, context-window, or another non-continuity error
- **THEN** the client MUST NOT convert it into a stale-anchor full-context retry
- **AND** codex-lb MUST preserve the original error class as much as safely possible

### Requirement: Codex WebSocket continuity source of truth is centralized
The behavior for Codex-native WebSocket previous-response continuity MUST be specified in this OpenSpec change rather than route-local or branch-local ad hoc patches. Future changes to this behavior MUST update the OpenSpec requirements before modifying code.

#### Scenario: Previous-response fix changes behavior
- **WHEN** a patch changes routing, replay, masking, retry, or failure behavior for Codex-native WebSocket `previous_response_id`
- **THEN** the patch includes an OpenSpec delta or updates the active continuity source of truth
- **AND** direct `/backend-api/codex/responses` WebSocket tests or Codex client WebSocket tests cover the changed behavior

### Requirement: Direct WebSocket previous-response misses never leak raw upstream errors
When a direct Responses WebSocket request depends on `previous_response_id`, the service MUST NOT send a raw upstream `previous_response_not_found` payload to the downstream client. This applies to `/v1/responses` and `/backend-api/codex/responses` WebSocket clients.

#### Scenario: Codex Desktop continue receives upstream previous-response miss before response.created
- **WHEN** a direct WebSocket `response.create` request includes `previous_response_id`
- **AND** upstream emits a top-level `type=error` payload with `code=previous_response_not_found` or `param=previous_response_id`
- **AND** no stable upstream `response.id` has been assigned yet
- **THEN** the downstream client receives either a transparent replay result or a retryable terminal event
- **AND** the downstream payload does not include `previous_response_not_found`
- **AND** the downstream payload does not include the missing previous response id

#### Scenario: Codex Desktop continue has only request-log owner metadata
- **WHEN** a prior direct WebSocket turn completed and was persisted only in `request_logs`
- **AND** a later direct WebSocket follow-up references that completed response id
- **THEN** owner lookup uses request-log metadata or fails closed with a retryable error
- **AND** it does not continue on an unpinned account
- **AND** it does not expose raw `previous_response_not_found`

### Requirement: Failed precreated HTTP bridge replay retires stale sessions

When an HTTP bridge request is still pending before upstream `response.completed` and the upstream websocket closes or times out before the pending request can be completed, the service MUST fail the pending request terminally and retire the affected bridge session if precreated replay does not reconnect and resend successfully.

#### Scenario: Precreated replay fails after upstream disconnect

- **WHEN** an HTTP bridge request is pending before `response.completed`
- **AND** the upstream websocket closes before the request completes
- **AND** precreated replay fails to reconnect and resend the request
- **THEN** the pending request is removed from the bridge queue
- **AND** the per-session response-create gate is released
- **AND** the bridge session is closed and removed from local reuse
- **AND** the terminal error preserves the original failure code such as `stream_incomplete` or `upstream_request_timeout`

#### Scenario: Terminal logging failure does not preserve stale bridge ownership

- **WHEN** a failed pending HTTP bridge request is being logged as terminal
- **AND** request-log writing fails
- **THEN** the service still removes the stale bridge session from local reuse
- **AND** the service releases any durable bridge ownership for that stale session

#### Scenario: Concurrent waiter cannot submit on retired stale bridge

- **WHEN** an HTTP bridge request is waiting on a session response-create gate
- **AND** the upstream reader retires that same bridge session after a failed precreated replay
- **THEN** the waiting request or prewarm is rejected before it is appended to pending requests or sent upstream
- **AND** the retired bridge session remains closed and removed from local reuse
- **AND** the post-admission ownership check, pending enqueue, and upstream send are mutually exclusive with stale-session retirement

#### Scenario: Unregistered stale bridge reference cannot submit after admission

- **WHEN** an HTTP bridge request or prewarm holds a stale bridge session reference
- **AND** that bridge session is no longer the registered local owner for its session key
- **THEN** the request is rejected after response-create gate admission and before it is appended or sent upstream
- **AND** response-create gate and admission state acquired by the rejected request is released

#### Scenario: Unregistered closed bridge reference cannot reconnect

- **WHEN** an HTTP bridge request holds a closed stale bridge session reference
- **AND** that bridge session is no longer the registered local owner for its session key
- **THEN** the request is rejected before attempting to reconnect the stale bridge upstream

#### Scenario: Reader crash closes bridge before releasing pending gate

- **WHEN** an HTTP bridge upstream reader crashes while a pending request owns the response-create gate
- **AND** another request or prewarm is waiting on that same gate
- **THEN** the crashed bridge session is marked closed before the pending request gate is released
- **AND** the waiting request or prewarm cannot submit on the crashed bridge
- **AND** the crashed bridge session is removed from local reuse and its upstream resources are closed

#### Scenario: Prewarm cleanup does not consume visible queue slots

- **WHEN** a prewarm request is rejected or interrupted after response-create gate admission
- **AND** a visible HTTP bridge request is still counted in the session queue
- **THEN** prewarm cleanup releases its response-create gate and admission state
- **AND** the visible request queue count is preserved

### Requirement: Pre-dispatch Responses requests recover from local network transitions

When a Responses request encounters a classified local DNS or host-route failure and the transport proves that request dispatch did not occur, the proxy MUST retry on the same account with bounded backoff until the attempt succeeds or the existing request budget expires. A classified token-refresh network failure MUST receive the same bounded same-account recovery only when typed transport provenance proves the refresh POST was not dispatched. Recovery MUST NOT move account-owned continuation or file state to another account. Recovery client rotation, client construction, cleanup, and sleep MUST remain inside the original monotonic deadline, and existing keepalive behavior MUST remain active while an HTTP/SSE client waits. Post-connect send or receive failures, response/body-read failures, and serialized terminal response events with uncertain upstream delivery MUST retain the account-neutral network classification but MUST NOT be transparently replayed.

#### Scenario: HTTP stream survives a temporary DNS outage

- **WHEN** a streaming Responses request fails DNS resolution before request dispatch
- **AND** DNS resolution recovers before the request budget expires
- **THEN** the proxy retries the request on the same account
- **AND** the downstream stream receives the recovered upstream response instead of a terminal network error

#### Scenario: Native WebSocket connect survives a temporary DNS outage

- **WHEN** a native Responses WebSocket request cannot open its upstream WebSocket because of a classified local network failure
- **AND** connectivity recovers before the request budget expires
- **THEN** the proxy opens the upstream WebSocket on the same account
- **AND** does not exhaust or exclude unrelated accounts

#### Scenario: Recovery remains bounded

- **WHEN** the local network does not recover before the configured request budget expires
- **THEN** the proxy terminates the request with `error.code = "upstream_request_timeout"` and message `"Proxy request budget exhausted"`
- **AND** does not extend the deadline or replay downstream-visible output

#### Scenario: Token refresh survives a temporary DNS outage

- **WHEN** token refresh for the selected account reports a classified process-network failure
- **AND** typed transport provenance proves the refresh POST was not dispatched
- **AND** connectivity recovers within the original request deadline
- **THEN** the proxy retries refresh on the same account
- **AND** does not record the network failure against the account

#### Scenario: Token refresh response failure is not replayed

- **WHEN** token refresh reports a classified process-network failure while reading the response or body
- **AND** the proxy cannot prove the refresh POST was not dispatched
- **THEN** the failure retains the account-neutral process-network code
- **AND** the proxy does not retry the possibly consumed rotating refresh token

#### Scenario: Ambiguous compact POST failure is not replayed

- **WHEN** a compact POST reports a classified process-network failure without typed pre-dispatch provenance
- **THEN** the compact failure retains the account-neutral process-network code
- **AND** the proxy does not replay, penalize, or exclude the selected account

#### Scenario: Serialized terminal network failure is not replayed

- **WHEN** an upstream stream emits a terminal response event carrying the process-network code
- **AND** the proxy cannot prove that request dispatch did not occur
- **THEN** the terminal event is surfaced without transparent replay
- **AND** the selected account's health remains unchanged

#### Scenario: Post-connect WebSocket network failure is not replayed speculatively

- **WHEN** an upstream WebSocket send or receive reports a classified process-network failure after the connection opened
- **AND** the proxy cannot prove that `response.create` was not delivered
- **THEN** the pending request fails with the account-neutral process-network code
- **AND** the proxy does not transparently replay the request

### Requirement: Native `/backend-api/codex` routes accept the Codex tool surface
The service MUST accept native `/backend-api/codex/responses` HTTP and websocket requests that include the Codex Desktop tool surface. This includes custom tools plus built-in Codex tool types such as `image_generation`, `file_search`, `code_interpreter`, and `computer_use_preview`. The service MUST continue normalizing `web_search_preview` to `web_search` before forwarding upstream. OpenAI-style `/v1/*` routes MUST keep rejecting unsupported built-in tools with an `invalid_request_error`.

#### Scenario: Auto transport prefers HTTP for image-generation tool requests
- **WHEN** the resolved upstream transport strategy is `"auto"`
- **AND** the request includes a built-in `image_generation` tool
- **THEN** the proxy chooses the upstream HTTP/SSE transport even if the model would otherwise prefer websocket

#### Scenario: backend responses accept native built-in and custom tools
- **WHEN** a client sends `/backend-api/codex/responses` with tools including `{"type":"custom","name":"exec"}` and `{"type":"image_generation"}`
- **THEN** the service accepts the request and forwards the tools upstream without returning an `invalid_request_error`

#### Scenario: v1 responses continue rejecting unsupported built-in tools
- **WHEN** a client sends `/v1/responses` with `tools=[{"type":"image_generation"}]`
- **THEN** the service returns a 4xx OpenAI `invalid_request_error` indicating the unsupported tool type

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

### Requirement: Continuity-dependent Responses follow-ups fail closed with retryable errors
When a Responses follow-up depends on previously established continuity state, the service MUST return a retryable continuity error if that continuity cannot be reconstructed safely. The service MUST NOT expose raw `previous_response_not_found` for bridge-local metadata loss or similar internal continuity gaps.

#### Scenario: HTTP bridge loses local continuity metadata for a follow-up request
- **WHEN** an HTTP `/v1/responses` or `/backend-api/codex/responses` follow-up request depends on `previous_response_id` or a hard continuity turn-state
- **AND** the bridge cannot reconstruct the matching live continuity state from local or durable metadata
- **THEN** the service returns a retryable OpenAI-format error
- **AND** the error code is not `previous_response_not_found`

#### Scenario: in-flight bridge follower loses continuity while waiting on the same canonical session
- **WHEN** a follow-up request waits on an in-flight HTTP bridge session for the same hard continuity key
- **AND** the bridge still cannot reconstruct safe continuity state once the leader finishes
- **THEN** the service returns a retryable OpenAI-format error
- **AND** the error code is not `previous_response_not_found`

#### Scenario: multiplexed follow-ups fail closed only for the matching continuity anchor
- **WHEN** a websocket or HTTP bridge session has multiple pending follow-up requests with different `previous_response_id` anchors
- **AND** continuity loss is detected for exactly one of those anchors
- **THEN** the service applies the retryable fail-closed continuity error only to the matching follow-up request
- **AND** it does not expose raw `previous_response_not_found`
- **AND** unrelated pending requests continue on their own response lifecycle

#### Scenario: multiplexed follow-ups sharing one anchor fail closed together without leaking raw continuity errors
- **WHEN** a websocket or HTTP bridge session has multiple pending follow-up requests that share the same `previous_response_id` anchor
- **AND** upstream emits an anonymous continuity loss event such as `previous_response_not_found` for that shared anchor
- **THEN** the service rewrites each affected follow-up into a retryable continuity error
- **AND** no affected follow-up exposes raw `previous_response_not_found`
- **AND** the run remains usable for subsequent requests after the rewritten failures

#### Scenario: single pre-created follow-up still fails closed when continuity loss omits explicit response id in message
- **WHEN** a websocket follow-up request is pending with `previous_response_id` and has not received a stable upstream `response.id` yet
- **AND** upstream emits `previous_response_not_found` with `param=previous_response_id`
- **AND** the upstream error message omits the literal previous response identifier
- **THEN** the service still maps that continuity loss to the pending follow-up
- **AND** it rewrites the downstream terminal event to a retryable continuity error
- **AND** it does not surface raw `previous_response_not_found` to the client

### Requirement: Hard continuity owner lookup fails closed
When a request depends on hard continuity ownership, the service MUST fail closed if owner or ring lookup errors prevent safe pinning. The service MUST NOT continue with local recovery or account selection that bypasses hard owner enforcement.

#### Scenario: websocket previous-response owner lookup errors
- **WHEN** a websocket or HTTP fallback follow-up request includes `previous_response_id`
- **AND** owner lookup errors prevent the proxy from determining the required owner account
- **THEN** the service returns a retryable OpenAI-format error
- **AND** it does not continue the request on an unpinned account

#### Scenario: bridge owner or ring lookup errors for hard continuity keys
- **WHEN** an HTTP bridge request uses a hard continuity key such as turn-state, explicit session affinity, or `previous_response_id`
- **AND** owner or ring lookup errors prevent the proxy from proving the correct bridge owner
- **THEN** the service returns a retryable OpenAI-format error
- **AND** it does not create or recover a local bridge session on the current replica

### Requirement: Codex backend session_id preserves account affinity
When a backend Codex Responses or compact request includes a non-empty accepted session header, the service MUST use that value as the routing affinity key for upstream account selection. If the request lacks a client-supplied `prompt_cache_key`, the service MUST derive and attach a stable `prompt_cache_key` before upstream forwarding so account affinity and upstream prompt-cache routing can coexist. Accepted session headers are `session_id`, `x-codex-session-id`, and `x-codex-conversation-id`, in that priority order.

#### Scenario: Backend Codex request derives prompt_cache_key before codex-session routing
- **WHEN** `/backend-api/codex/responses` is called with `session_id` and without `prompt_cache_key`
- **THEN** the routing decision still uses durable `codex_session` affinity for account selection
- **AND** the forwarded upstream payload includes a derived stable `prompt_cache_key`

### Requirement: Proxy-generated prompt cache key derivation is operator-toggleable
The service MUST provide a runtime flag that disables only proxy-generated prompt-cache-key derivation. When disabled, the service MUST continue forwarding any client-supplied `prompt_cache_key` unchanged and MUST NOT synthesize a new one.

#### Scenario: Derivation disabled preserves client-supplied key
- **WHEN** the derivation flag is disabled and a client sends `prompt_cache_key`
- **THEN** the service forwards that key unchanged
- **AND** it does not generate a replacement key

### Requirement: Pre-commit ambiguous websocket 403 failures fail over by account

When a Responses-serving path has not yet emitted downstream bytes, events, or frames, the service MUST treat an ambiguous upstream websocket connect `403` as an account-scoped failure rather than immediately surfacing it to the client. The retry MUST stay on the same upstream transport family; the service MUST NOT silently downgrade to HTTP only because a websocket connect attempt returned `403`.

#### Scenario: Websocket connect 403 fails over to another eligible account

- **WHEN** the proxy selects an account for a Responses request that requires an upstream websocket connect
- **AND** the upstream websocket connect fails with HTTP `403`
- **AND** the failure does not carry a permanent deactivation signal
- **AND** the proxy has not yet emitted any downstream bytes, events, or frames
- **AND** another eligible account exists
- **THEN** the proxy places the failed account into a temporary runtime cooldown for websocket-connect selection
- **AND** it retries the same request against another eligible account on the same transport family
- **AND** it does not silently downgrade to HTTP only because of that `403`

#### Scenario: Final ambiguous websocket connect 403 remains visible

- **WHEN** a pre-commit upstream websocket connect fails with HTTP `403`
- **AND** no other eligible account can serve the request
- **THEN** the proxy surfaces the final upstream `403` to the client
- **AND** the proxy records the failure as a client-exposed pre-commit upstream error

### Requirement: Fresh websocket replays avoid failed accounts
When an upstream websocket closes or rejects send while a pre-created Responses request can be replayed as a fresh request, the service MUST record a transient upstream stream error for the failed account and MUST exclude that account from account selection for the replay reconnect.

#### Scenario: replay reconnect skips account that dropped the socket
- **WHEN** a direct Responses websocket request is pending without previous_response_id
- **AND** the upstream websocket closes before the request receives a terminal response event
- **AND** the request is eligible for transparent replay
- **THEN** the service records a transient stream error for the account that dropped the socket
- **AND** the replay reconnect excludes that account from selection

#### Scenario: previous-response replay keeps owner affinity
- **WHEN** a direct Responses websocket follow-up request includes previous_response_id
- **AND** the upstream websocket closes before the request receives a terminal response event
- **AND** the request is eligible for transparent replay
- **THEN** the service records a transient stream error for the account that dropped the socket
- **AND** the replay reconnect does not exclude the previous-response owner account solely because it dropped the socket

### Requirement: Upstream websocket handshakes exclude HTTP content-negotiation headers

The service MUST exclude the HTTP content-negotiation headers `accept` and
`content-type`, hop-by-hop headers, and websocket handshake control headers
(`sec-websocket-*`, `accept-encoding`, `cookie`) whenever it builds upstream
websocket handshake headers from inbound HTTP request headers, including HTTP
responses bridge session creation and bridge session reconnection. Internal
websocket protocol headers set by the service itself (such as the responses
websocket beta header) are not affected.

#### Scenario: bridge session creation filters content-negotiation headers

- **WHEN** the HTTP responses bridge opens an upstream websocket session for a
  downstream request carrying `accept: text/event-stream` and
  `content-type: application/json`
- **THEN** the upstream websocket handshake headers exclude `accept` and
  `content-type`
- **AND** non-excluded end-to-end headers are still forwarded

#### Scenario: bridge session reconnection filters content-negotiation headers

- **WHEN** the HTTP responses bridge reconnects an upstream websocket session
  using stored inbound headers that include `accept` and `content-type`
- **THEN** the rebuilt upstream websocket handshake headers exclude `accept`
  and `content-type`

### Requirement: Codex compaction outputs preserve upstream item identity

When Codex-affinity compaction selects an upstream compaction output item with opaque `encrypted_content` and a non-empty string `id`, the proxy MUST preserve that exact `id` with the encrypted content in the normalized compaction item. The proxy MUST NOT invent or replace a compaction item ID. The preserved normalized item MUST be identical across the direct Codex compact JSON response and both compaction item locations in a terminal-trigger SSE response. Public OpenAI-style compact behavior MUST remain unchanged.

#### Scenario: Direct Codex compact response preserves the upstream ID

- **WHEN** `POST /backend-api/codex/responses/compact` receives an upstream compact result containing a compaction item with a non-empty string `id` and `encrypted_content`
- **THEN** the normalized single output item contains that exact `id` and encrypted content
- **AND** the proxy does not synthesize a replacement ID

#### Scenario: Terminal compaction trigger streams the preserved ID

- **WHEN** `POST /backend-api/codex/responses` ends with one valid `compaction_trigger` and upstream compact output includes a non-empty compaction item `id`
- **THEN** `response.output_item.done.item` contains the exact upstream `id`
- **AND** `response.completed.response.output` contains the same normalized item

#### Scenario: Missing upstream ID remains missing

- **WHEN** the selected upstream compaction result contains encrypted content without a non-empty string `id`
- **THEN** the normalized compaction item omits `id`
- **AND** the proxy does not invent one

### Requirement: Estimable context overflow is rejected before upstream connection

The proxy MUST return HTTP 400 with an OpenAI error envelope using code
'context_length_exceeded' and type 'invalid_request_error' when a normalized
Responses request has an estimable inline context whose estimated input tokens
reach the conservative guard limit for the effective model context window.
The rejection MUST occur before admission, account selection, or upstream
connection. Opaque prior-response, conversation, and file/image contexts MAY
remain on the existing upstream handling path when their complete size is not
locally knowable. A well-formed compaction-lane request — one whose final
top-level input item is a single terminal `compaction_trigger` — MUST bypass
the guard on every guarded path (HTTP stream, HTTP collect, and websocket
`response.create`) so that remote-compaction recovery is never rejected by the
guard it is recovering from. Malformed trigger placement MUST NOT receive the
exemption.

#### Scenario: Spark request is rejected locally

- **GIVEN** the effective context window for 'gpt-5.3-codex-spark' is 128000
- **AND** the normalized inline input estimate reaches the configured guard
  threshold
- **WHEN** a Responses request is received
- **THEN** the proxy returns 400 with 'error.code=context_length_exceeded'
- **AND** no upstream account connection is attempted

#### Scenario: Opaque context is not guessed

- **GIVEN** a request includes a prior-response or conversation anchor, or an
  opaque file/image reference
- **WHEN** the proxy cannot estimate the complete upstream context
- **THEN** the proxy preserves the existing upstream handling path

#### Scenario: Compaction-lane request bypasses the guard

- **GIVEN** a Responses request whose estimated inline input reaches the guard
  threshold
- **AND** its final top-level input item is a single `compaction_trigger`
- **WHEN** the request is received on the HTTP or websocket responses path
- **THEN** the guard does not reject the request
- **AND** the request proceeds to compaction handling

#### Scenario: Malformed trigger placement is not exempt

- **GIVEN** a Responses request whose estimated inline input reaches the guard
  threshold
- **AND** it contains a `compaction_trigger` that is duplicated or not the
  final top-level input item
- **WHEN** the request is received
- **THEN** the request does not receive the guard exemption

### Requirement: Proxy-injected continuity anchors preserve reasoning pairing
When the service rewrites a client's self-contained websocket full replay into a proxy-injected `previous_response_id` plus a sliced input delta, it MUST verify that the sliced delta is reasoning-consistent before using it. A delta is reasoning-consistent unless it contains an assistant `message` item that is not preceded by a `reasoning` item within the same delta; re-sent `reasoning` items without a following message and complete `reasoning`-then-`message` groups are consistent because upstream accepts and dedupes them on anchored turns. If the delta would not be reasoning-consistent, the service MUST skip anchor injection for that request and forward the client's original full replay unchanged, and it MUST log a distinct skip reason for observability.

#### Scenario: slice boundary would orphan an assistant message from its reasoning item
- **WHEN** a websocket `/backend-api/codex/responses` request has no `previous_response_id` and its input prefix matches the stored continuity fingerprint
- **AND** the sliced delta `input[stored_count:]` begins with or contains an assistant `message` item whose paired `reasoning` item lies before the slice boundary
- **THEN** the service does not inject `previous_response_id`
- **AND** the request is forwarded upstream with the client's original full input
- **AND** the service logs an anchor-injection skip with a reasoning-orphan reason

#### Scenario: reasoning-consistent delta still uses the anchor
- **WHEN** a websocket `/backend-api/codex/responses` request has no `previous_response_id` and its input prefix matches the stored continuity fingerprint
- **AND** the sliced delta contains only self-consistent items (for example tool outputs whose calls are anchored upstream, or complete reasoning+message groups)
- **THEN** the service injects `previous_response_id` and forwards the sliced delta as today

#### Scenario: reasoning-led incremental delta keeps the anchor
- **WHEN** a websocket `/backend-api/codex/responses` request has no `previous_response_id` and its input prefix matches the stored continuity fingerprint
- **AND** the sliced delta begins with the prior turn's outputs (`reasoning` items, tool calls, and their outputs) followed by new user input, with any assistant `message` preceded by a `reasoning` item within the delta
- **THEN** the service injects `previous_response_id` and forwards the sliced delta

### Requirement: Orphaned-reasoning rejections of proxy-injected anchors recover via full replay
When upstream rejects a websocket turn with an `invalid_request_error` stating that an item was provided without its required `reasoning` item, and the service injected the `previous_response_id` for that turn while retaining a retry-safe self-contained full replay body, the service MUST treat the failure like a stale-anchor continuity loss: reconnect and replay the retained full payload as a fresh turn without `previous_response_id` instead of forwarding the raw upstream error. If no retry-safe full replay body was retained, the service MUST surface a retryable continuity failure rather than the raw upstream invalid-request error. Client-authored payloads whose anchors were not proxy-injected MUST NOT trigger this recovery and continue to receive the upstream error unchanged.

#### Scenario: proxy-injected anchor turn hits the orphaned-reasoning 400
- **WHEN** the service injected `previous_response_id` into a websocket turn and retained a retry-safe full replay body
- **AND** upstream emits `invalid_request_error` with a message matching "was provided without its required 'reasoning' item" before `response.created`
- **THEN** the service reconnects the upstream websocket
- **AND** it replays the retained full payload without `previous_response_id`
- **AND** the downstream client receives the recovered response events, not the raw invalid-request error
- **AND** the service logs that the orphaned-reasoning recovery replay fired

#### Scenario: orphaned-reasoning 400 without a retained replay body
- **WHEN** the service injected `previous_response_id` into a websocket turn but no retry-safe full replay body was retained
- **AND** upstream emits the orphaned-reasoning `invalid_request_error` before `response.created`
- **THEN** the downstream client receives a retryable continuity failure rather than the raw upstream invalid-request error

#### Scenario: client-authored anchor is not rewritten
- **WHEN** a websocket turn carries a client-authored `previous_response_id` that the service did not inject
- **AND** upstream emits the orphaned-reasoning `invalid_request_error`
- **THEN** the service forwards the upstream error to the client unchanged

### Requirement: Direct WebSocket replay never mixes numeric response sequences

For direct Responses WebSocket requests, the proxy MUST NOT transparently replay a request on a fresh upstream generation after any finite integer `sequence_number` frame for that request has been successfully sent downstream, except for the verified no-generation prewarm case defined below. When an upstream close would otherwise trigger replay, the proxy MUST settle the failed pending request without emitting frames from a new upstream generation under the existing downstream response id, and MUST close the downstream WebSocket with code 1011 so the client can retry on a fresh transport. When an upstream terminal error would otherwise trigger quota, authentication, security-work, or equivalent replay, the proxy MUST finalize and surface that terminal error without reconnecting. Suppressed frames and non-integer sequence sentinels MUST NOT by themselves disable otherwise-safe replay.

The sole numeric-sequence exception MUST require `request_kind = "prewarm"`, a literal normalized `generate = false`, exactly one recorded `response.created`, no visible output, sequence watermark `0`, a single pending request, and the existing one-shot replay eligibility. The proxy MUST suppress the replayed `response.created` and MUST NOT renumber or synthesize sequences. If a later replay event has a finite integer sequence that does not advance beyond the exposed watermark, the proxy MUST settle it as `stream_incomplete`, emit no synthetic terminal frame, and close downstream with code 1011.

#### Scenario: Sequenced model-generating response is interrupted

- **WHEN** a direct WebSocket model-generating request has emitted
  `response.created` or another frame with a finite integer `sequence_number`
- **AND** upstream closes before a terminal response event
- **THEN** codex-lb does not transparently replay that request under the
  existing downstream response id
- **AND** no lower replay sequence is emitted downstream
- **AND** the downstream WebSocket closes with code 1011

#### Scenario: Prewarm metadata without generate-false body is not sufficient

- **WHEN** a direct WebSocket request claims `request_kind = "prewarm"`
- **BUT** its normalized body does not contain the literal `generate = false`
- **AND** a numeric sequence has been sent downstream
- **THEN** codex-lb does not transparently replay the request

#### Scenario: Progressed prewarm is not replayed

- **WHEN** a verified no-generation prewarm has emitted `response.created` and
  any additional `response.*` progress event
- **AND** upstream closes before completion
- **THEN** codex-lb does not transparently replay the request
- **AND** the downstream WebSocket closes with code 1011

#### Scenario: Replayed prewarm sequence must advance

- **GIVEN** a verified no-generation prewarm is replayed after exposing
  `response.created` at sequence `0`
- **WHEN** a non-suppressed replay frame has a finite integer
  `sequence_number <= 0`
- **THEN** codex-lb emits no frame from that replay generation downstream
- **AND** it settles the request as `stream_incomplete`
- **AND** it closes the downstream WebSocket with code 1011

#### Scenario: Unsafe replay settles request ownership

- **WHEN** sequenced replay is refused after upstream close or a replay
  sequence fails to advance
- **THEN** response-create admission, account-local leases, API-key
  reservations, and request logging are finalized exactly once
- **AND** the failed attempt does not become a successful continuity owner

#### Scenario: Sequenced retryable terminal event is not replayed

- **WHEN** a direct WebSocket request has successfully emitted a finite integer
  `sequence_number`
- **AND** upstream emits a terminal error that would ordinarily trigger
  transparent quota, authentication, or security-work replay
- **THEN** codex-lb does not reconnect or resend the request
- **AND** the terminal error is finalized and remains client-visible under the
  existing error contract

#### Scenario: Sequence-free startup remains replayable

- **WHEN** upstream closes before any numeric sequence-bearing frame has been
  successfully sent downstream
- **AND** the request otherwise satisfies the existing one-shot replay guard
- **THEN** codex-lb MAY transparently replay the request on a fresh upstream
  connection

#### Scenario: Suppressed frame does not establish exposure

- **WHEN** codex-lb suppresses an upstream frame before downstream emission
- **AND** the suppressed frame contains a numeric `sequence_number`
- **THEN** that frame does not establish the downstream sequence watermark

### Requirement: Opaque-context detection tolerates arbitrary JSON

When deciding whether a Responses request contains opaque context that prevents local input estimation, the proxy MUST classify a mapping as an opaque `input_file` or `input_image` content item only when the mapping's `type` value is a string equal to one of those identifiers. A mapping containing a `file_id` key MUST still be treated as opaque. All other JSON values, including JSON Schema fragments where a `type` key maps to an object or array (for example `{"properties": {"type": {"const": "preview"}}}`), MUST be traversed recursively without raising an error.

#### Scenario: Tool schema with object-valued type key does not crash the guard

- **GIVEN** a Responses request whose function-tool JSON Schema contains
  `{"properties": {"type": {"const": "preview"}}}`
- **WHEN** context-window enforcement estimates the request
- **THEN** estimation completes without error
- **AND** the schema fragment is not classified as opaque context

#### Scenario: Opaque file and image items still skip estimation

- **GIVEN** a Responses request containing an `input_file` or `input_image`
  content item, or any mapping with a `file_id` key
- **WHEN** the proxy attempts local input estimation
- **THEN** the request is treated as opaque and preserved on the existing
  upstream handling path

### Requirement: Oversized response.create payloads are slimmed or rejected fail-fast before upstream send

When the service prepares a Responses `response.create` request for the upstream websocket, it MUST measure the serialized outbound request size before sending it upstream. If the payload exceeds the upstream websocket budget, the service MUST first attempt to slim only the historical portion of `input` that precedes the most recent user turn: historical inline images MUST be replaced with textual omission notices, and oversized historical tool outputs MUST be replaced with textual omission notices that preserve the item in sequence. Historical slimming MUST cover tool-call output items of every supported type — `function_call_output`, `custom_tool_call_output`, and `apply_patch_call_output` — including inline images nested inside list- or mapping-valued `output` content parts, which MUST be replaced with the image omission notice while non-image parts, item order, `call_id`, and `status` fields are preserved. If the request still exceeds budget after slimming, the service MUST fail locally with status `400` — not `413` — carrying `error.code = "payload_too_large"`, `error.type = "invalid_request_error"`, and `error.param = "input"`, because the official Codex client treats `400` as a non-retryable invalid-request error surfaced immediately while `413` triggers five full-payload retries followed by a sticky session-wide websocket-to-HTTP transport downgrade.

#### Scenario: Inline images nested in historical tool-call outputs are slimmed

- **GIVEN** an oversized `response.create` whose historical `input` contains a
  `custom_tool_call_output` (or `function_call_output` /
  `apply_patch_call_output`) whose `output` is a list of content parts
  including `data:image/` inline images
- **WHEN** the size guard triggers historical slimming
- **THEN** each nested inline image part is replaced with the image omission
  notice part
- **AND** non-image parts, item order, `call_id`, and `status` are preserved
- **AND** the slimmed request is forwarded upstream when it fits the budget

#### Scenario: Oversized string outputs are slimmed for all tool-call output types

- **GIVEN** a historical `custom_tool_call_output` or `apply_patch_call_output`
  whose string `output` exceeds the oversized-tool-output threshold
- **WHEN** the size guard triggers historical slimming
- **THEN** the string output is replaced with the tool-output omission notice,
  matching the existing `function_call_output` behavior

### Requirement: Responses Lite signaling enforces all-turns reasoning context

Every final upstream Responses payload that codex-lb advertises as Responses Lite—by the canonical HTTP header or the canonical per-request websocket client-metadata marker, whether body-derived, bridge-preserved, or continuity-trusted—MUST contain the exact JSON string `reasoning.context = "all_turns"`. Before upstream serialization, the service MUST create a reasoning object when it is omitted or null and MUST replace an absent, null, blank, differently-cased, otherwise different-string, or non-string context value with `"all_turns"`. It MUST preserve `reasoning.effort`, `reasoning.summary`, and every unrelated reasoning member.

This normalization MUST be idempotent, MUST NOT establish Lite classification or continuity trust, MUST NOT reject an otherwise-valid Lite request solely for a context mismatch, and MUST NOT remove the Lite signal. For requests not advertised as Lite, this normalization MUST leave the client-supplied reasoning shape unchanged. An invalid non-object reasoning container remains subject to the existing client-payload validation contract.

#### Scenario: Body-derived Lite HTTP request omits reasoning

- **WHEN** a normalized HTTP Responses body contains an `additional_tools` input item and omits or nulls `reasoning`
- **THEN** the final upstream HTTP body contains `reasoning.context = "all_turns"`
- **AND** the request carries the canonical Responses Lite HTTP header

#### Scenario: Existing Lite reasoning members survive normalization

- **WHEN** a Responses Lite body includes reasoning effort, summary, or extension members and its context is absent, null, blank, differently cased, another string, or a non-string value
- **THEN** the final upstream body contains the exact string `reasoning.context = "all_turns"`
- **AND** every unrelated reasoning member retains its client-supplied value

#### Scenario: Compact Lite request uses the same invariant

- **WHEN** a compact request is advertised upstream as Responses Lite
- **THEN** its final upstream POST body contains `reasoning.context = "all_turns"`
- **AND** it carries the canonical Responses Lite HTTP header

#### Scenario: Websocket and HTTP fallback agree on Lite reasoning

- **WHEN** a body-derived Lite request is prepared for upstream websocket transport
- **THEN** its `response.create` body contains both the canonical Lite client-metadata marker and `reasoning.context = "all_turns"`
- **BUT WHEN** the websocket handshake falls back to upstream HTTP
- **THEN** the HTTP body retains `reasoning.context = "all_turns"`, the marker is absent, and the canonical Lite HTTP header is present

#### Scenario: HTTP bridge transformations preserve the invariant

- **GIVEN** an HTTP bridge request established Lite mode from an `additional_tools` prefix
- **WHEN** bridge trimming or retry builds a final `response.create` body whose input delta no longer contains that prefix
- **THEN** the body retains the internally derived canonical Lite marker
- **AND** it contains `reasoning.context = "all_turns"`

#### Scenario: Trusted marker-only continuation is normalized

- **GIVEN** a same-model websocket continuation has trusted Lite continuity to its referenced previous response
- **WHEN** its incremental body carries the canonical marker but omits the original `additional_tools` prefix
- **THEN** the final upstream body contains `reasoning.context = "all_turns"`
- **AND** the canonical marker remains present

#### Scenario: Untrusted and non-Lite requests are not normalized

- **WHEN** a non-Lite request supplies arbitrary reasoning context, an inbound Lite header, or a stale or otherwise untrusted websocket marker
- **THEN** the existing signal rules omit or strip the untrusted Lite signal
- **AND** this normalization does not alter the request's client-supplied reasoning shape

### Requirement: Responses HTTP ingress uses the expanded bounded budget

HTTP requests to `/v1/responses` and `/backend-api/codex/responses`, including trailing-slash variants, MUST use the larger of `max_decompressed_body_bytes` and `max_decompressed_responses_body_bytes` as both the raw-body and decompressed-body ingress budget. The Responses-specific default MUST remain 128 MiB.

The trailing-slash variants MUST be hidden aliases of the canonical HTTP handlers rather than redirects, so streamed bodies receive the same admission, authorization, and route behavior.

If either representation exceeds that budget, the service MUST stop before route logic or upstream forwarding and return HTTP 413 with an OpenAI-compatible error envelope carrying `error.code = payload_too_large` and `error.type = invalid_request_error`.

This transport-ingress 413 applies before parsing and is distinct from the existing application-level oversized-`response.create` guard. A request that fits the 128 MiB transport budget but still exceeds the upstream websocket budget after historical slimming MUST retain the existing HTTP 400 `payload_too_large` behavior and `param = input`.

#### Scenario: Larger Responses request fits both ingress checks

- **WHEN** a Responses HTTP request is larger than the general budget but no larger than the Responses budget in either raw or decompressed form
- **THEN** the ingress guards allow the request to continue to Responses route handling

#### Scenario: Trailing-slash Responses request is admitted without redirect

- **WHEN** a client sends a chunked HTTP request to `/v1/responses/` or `/backend-api/codex/responses/`
- **THEN** the service applies the same ingress budget and handler as the corresponding canonical path
- **AND** it does not return a trailing-slash redirect before consuming the guarded body

#### Scenario: Responses raw body exceeds its budget

- **WHEN** a Responses HTTP request's raw body exceeds the Responses budget
- **THEN** the service returns HTTP 413 with `error.code = payload_too_large` and `error.type = invalid_request_error`
- **AND** the service does not invoke Responses route logic or forward the request upstream

#### Scenario: Responses expanded body exceeds its budget

- **WHEN** an encoded Responses HTTP request fits the raw budget but expands beyond the Responses budget
- **THEN** the service returns HTTP 413 with `error.code = payload_too_large` and `error.type = invalid_request_error`
- **AND** the service does not invoke Responses route logic or forward the request upstream

#### Scenario: Post-slimming application rejection remains 400

- **WHEN** a Responses HTTP request fits the raw and decompressed transport-ingress budget
- **AND** its serialized `response.create` still exceeds the upstream websocket budget after historical slimming
- **THEN** the existing application-level guard returns HTTP 400 with `error.code = payload_too_large`, `error.type = invalid_request_error`, and `error.param = input`
