# responses-api-compat Specification

## Purpose

Define Responses API compatibility contracts so Codex, OpenCode, and OpenAI-style clients preserve expected behavior.
## Requirements
### Requirement: Internal Responses Lite header is forwarded upstream

The service MUST forward the inbound `X-OpenAI-Internal-Codex-Responses-Lite` header unchanged to upstream Responses, compact, or WebSocket transports. It MUST NOT remove the header to disable Responses Lite.

#### Scenario: HTTP and compact upstream headers preserve Lite

- **WHEN** a client sends a Responses or compact request with `X-OpenAI-Internal-Codex-Responses-Lite: 1`
- **THEN** the upstream HTTP request headers include `X-OpenAI-Internal-Codex-Responses-Lite: 1`
- **AND** existing authentication, proxy identity, and hop-by-hop header filtering remains in effect

#### Scenario: WebSocket upstream headers preserve Lite

- **WHEN** a client opens a Responses WebSocket with `X-OpenAI-Internal-Codex-Responses-Lite: 1`
- **THEN** the upstream WebSocket connection headers include `X-OpenAI-Internal-Codex-Responses-Lite: 1`
- **AND** existing WebSocket beta and Codex continuity headers are preserved

### Requirement: GPT-5.6 bootstrap metadata advertises Lite Code Mode capabilities

Static bootstrap metadata for `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna` MUST include `use_responses_lite=true`, `tool_mode=code_mode_only`, and `experimental_supported_tools=["exec", "wait"]`. The `multi_agent_version` MUST be `v2` for Sol and Terra and `v1` for Luna. A successful live catalog refresh MAY replace these fallback entries with upstream metadata.

#### Scenario: Offline GPT-5.6 model discovery preserves tool capabilities

- **GIVEN** the live upstream model catalog has not populated the registry
- **WHEN** a client requests `/backend-api/codex/models`
- **THEN** the GPT-5.6 Sol, Terra, and Luna entries include the Lite and Code Mode capability metadata
- **AND** each entry advertises `exec` and `wait` as experimental supported tools
- **AND** the entries retain their configured multi-agent version

### Requirement: Responses Lite tool definitions survive input normalization

The service MUST preserve each Responses Lite `type: "additional_tools"` input item, including its `role` and complete `tools` array, in the upstream payload. Instruction normalization MUST NOT move it into top-level `instructions` or drop it for lacking text.

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
OpenAI-style `/v1/responses`, `/v1/responses/compact`, and Responses-mapped chat completions MUST use non-empty `prompt_cache_key` for bounded upstream account affinity, despite `session_id` or disabled `sticky_threads_enabled`. Routes MUST NOT default to durable `CODEX_SESSION`. The key MUST pass upstream unchanged. Affinity MUST expire after the dashboard freshness window, adjustable without restart, so old keys can rebalance.

#### Scenario: OpenAI-style route ignores session header for durable codex-session pinning
- **WHEN** a client sends `/v1/responses` or `/v1/responses/compact` with a non-empty `session_id` header and no explicit sticky-thread mode
- **THEN** the service does not persist a durable `codex_session` mapping solely from that header
- **AND** bounded prompt-cache affinity behavior remains in effect

#### Scenario: dashboard prompt-cache affinity TTL is applied
- **WHEN** an operator updates the dashboard prompt-cache affinity TTL
- **THEN** subsequent OpenAI-style prompt-cache affinity decisions use the new freshness window

### Requirement: Responses requests reject uploaded input_image references

The system SHALL accept and forward `input_file` items with `file_id: "file_*"` verbatim on `/v1/responses`, `/backend-api/codex/responses`, and `/responses/compact`. For `input_image` with `file_id` or `image_url` starting `sediment://`, the proxy MUST return HTTP 400 `error.code = "unsupported_input_image_format"`, explaining that upstream Responses only accepts inline `data:` URLs for `input_image`.

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

### Requirement: Uploaded input_image rejection does not reshape conversation content

`app/core/openai/requests.py::extract_input_image_file_references` MAY detect unsupported uploaded `input_image` shapes. This request path MUST NOT fetch uploads, inline-convert images, or trim, slim, rewrite, or otherwise reshape inbound conversation content.

#### Scenario: Rejected image leaves conversation content untouched

- **WHEN** an `input_image` part references a `file_id` or `sediment://` URL
- **THEN** rejection does not fetch the upload or inline-convert the image
- **AND** no inbound conversation content is trimmed, slimmed, rewritten, or otherwise reshaped

### Requirement: Oversized responses request payloads fall back to HTTP
When `upstream_stream_transport` is `"auto"` and the serialized payload exceeds the WebSocket frame budget, the proxy MUST use upstream HTTP `POST`. If the request would otherwise use the enabled HTTP responses bridge, the proxy MUST bypass it for that request only and use raw HTTP. Explicit `upstream_stream_transport` overrides MUST still take precedence.

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

If the HTTP responses bridge sees upstream websocket `close_code = 1000` before surfacing any `response.*` event for the pending request, the proxy MUST classify it as rejected input and return HTTP 502 `upstream_rejected_input`. It MUST NOT trigger `retry_precreated` or `retry_fresh_upstream`.

#### Scenario: clean close before response.created is not retried

- **WHEN** upstream closes the HTTP responses bridge with `close_code = 1000` before any `response.*` event for the pending request
- **THEN** the proxy returns HTTP 502 with `error.code = "upstream_rejected_input"`
- **AND** does not transparently replay the pre-created request

### Requirement: Long Codex websocket turns tolerate extended upstream silence
The default compact request budget MUST be at least 180 seconds, and the default upstream stream idle timeout MUST be at least 600 seconds, allowing long compaction or tool execution.

#### Scenario: compact and stream watchdog defaults leave room for long turns
- **WHEN** the service starts with default configuration
- **THEN** `compact_request_budget_seconds` is at least 180 seconds
- **AND** `stream_idle_timeout_seconds` is at least 600 seconds

### Requirement: Upstream websocket drops penalize affected accounts

On upstream websocket close with streamed requests pending before a terminal event, the proxy MUST record a transient upstream account error before signaling failure. Classified process-wide network failures instead MUST remain account-neutral and use their network code. Other closes MUST surface `stream_incomplete`, except sequenced direct requests governed by 'Sequenced direct WebSocket drops settle without synthetic terminal frames'.

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

### Requirement: Sequenced direct WebSocket drops settle without synthetic terminal frames

On upstream close before termination, except classified process-wide network failure, a direct Responses WebSocket request that successfully emitted a finite integer `sequence_number` MUST record `stream_incomplete` without a synthetic terminal under the active response id, then close downstream with 1011. This does not apply if verified no-generation prewarm recovery applies and its one-shot replay succeeds.

#### Scenario: Sequenced request closes without terminal synthesis

- **WHEN** an ordinary upstream close interrupts a direct request after successful finite integer sequence emission
- **AND** verified no-generation prewarm replay does not recover it
- **THEN** the request records `stream_incomplete` without a synthetic terminal frame under the active response id
- **AND** the downstream WebSocket closes with code 1011

### Requirement: Single HTTP bridge previous-response misses recover or fail closed
For an anonymous upstream `previous_response_not_found` error on a single pending HTTP bridge follow-up, the service MUST treat it as internal continuity loss. It MUST use the existing previous-response rebind recovery or rewrite the error as a retryable continuity failure, rather than forward the raw upstream invalid-request error.

#### Scenario: single pending HTTP bridge follow-up loses previous-response continuity
- **WHEN** an HTTP `/v1/responses` or `/backend-api/codex/responses` bridge session has exactly one pending request with `previous_response_id`
- **AND** upstream emits `previous_response_not_found` without a `response.id`
- **THEN** the service attempts the existing previous-response recovery path
- **AND** if recovery is unavailable, it emits a retryable continuity failure for that request
- **AND** the downstream error code is not `previous_response_not_found`

### Requirement: WebSocket full-resend previous-response misses retry without stale anchor
Direct WebSocket `response.create` with `previous_response_id` and self-contained full input MUST retain a safe replay body without that anchor. On `previous_response_not_found` before `response.created`, the service MUST reconnect and replay it fresh, not forward the raw error. Incremental tool-output-only input lacking its calls in the same request is not self-contained and MUST NOT replay fresh without `previous_response_id`.

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


### Requirement: WebSocket tool-search fresh retries require completed client-owned pairs

Direct WebSocket fresh retries MUST require ordered, self-contained `tool_search_call`/`tool_search_output` pairs with omitted/client execution. Status MUST be completed, omitted, or null. Others are incomplete. Calls MUST have dictionary `arguments`; outputs MUST have exactly one of list `tools` or string `output`. Server execution, missing preceding calls, incomplete/malformed pairs MUST be rejected. HTTP compact/fresh-resend policy and anchored WebSocket trimming MUST remain unchanged.

#### Scenario: Completed client-owned tool-search pair is retry-safe

- **GIVEN** a direct WebSocket full resend contains a completed `tool_search_call` with dictionary `arguments`
- **AND** a matching completed `tool_search_output` with a string `output` or a `tools` list
- **AND** both items omit `execution` or declare `execution: "client"`
- **WHEN** the proxy evaluates the payload for an anchor-free retry
- **THEN** the tool-search pair is accepted as self-contained replay state

#### Scenario: Server-owned tool-search output is not retry-safe

- **GIVEN** a direct WebSocket full resend contains a completed client-owned `tool_search_call`
- **AND** its matching `tool_search_output` declares `execution: "server"`
- **WHEN** the proxy evaluates the payload for an anchor-free retry
- **THEN** the request is not retained as a fresh retry

#### Scenario: Orphan or incomplete tool-search items are not retry-safe

- **GIVEN** a direct WebSocket full resend contains a `tool_search_output` without its matching preceding call, or a tool-search item whose status is neither `completed`, omitted, nor null
- **WHEN** the proxy evaluates the payload for an anchor-free retry
- **THEN** the request is not retained as a fresh retry

#### Scenario: Reused tool-search call IDs are not retry-safe

- **GIVEN** a direct WebSocket full resend reuses a tool-search `call_id` for a second call or a second output
- **WHEN** the proxy evaluates the payload for an anchor-free retry
- **THEN** the request is not retained as a fresh retry

### Requirement: WebSocket fresh retries omit response-owned tool-search IDs

Retained self-contained direct WebSocket `response.create` retries without `previous_response_id` MUST strip top-level `id` from every `tool_search_call`/`tool_search_output`. All other history, paired type, `call_id`, arguments/output, status, and order MUST remain unchanged. This applies to client and continuity-injected anchors. Retry preparation MUST NOT mutate caller input or ordinary anchored submissions.

#### Scenario: Client-supplied anchor retains a sanitized full-history retry

- **GIVEN** a direct Responses WebSocket request supplies `previous_response_id` and self-contained full history containing a paired `tool_search_call` and `tool_search_output` with response-owned IDs
- **WHEN** the proxy prepares both the ordinary anchored submission and its retained anchor-free retry
- **THEN** the ordinary anchored submission follows the existing trimming and forwarding behavior
- **AND** the retained retry preserves the complete original history and paired tool-search content without either tool-search `id`
- **AND** the inbound request remains unchanged

#### Scenario: Proxy-injected anchor retains a sanitized full-history retry

- **GIVEN** WebSocket continuity state lets the proxy replace a matching historical prefix with an injected `previous_response_id`
- **AND** that historical prefix contains a paired `tool_search_call` and `tool_search_output` with response-owned IDs
- **WHEN** the proxy retains the original payload for an anchor-free retry
- **THEN** the anchored submission still contains only the existing incremental delta
- **AND** the retained retry contains the complete original history and paired tool-search content without either tool-search `id`
- **AND** the inbound request remains unchanged

#### Scenario: Stale-anchor retry sends the sanitized retained body
- **GIVEN** the proxy retained a sanitized direct WebSocket fresh-retry body after a client-supplied or injected `previous_response_id`
- **WHEN** upstream rejects that anchored request with `previous_response_not_found` before `response.created`
- **THEN** the proxy reconnects and sends the retained sanitized body without `previous_response_id`
- **AND** the sent `tool_search_call` and `tool_search_output` items still have no top-level `id`

#### Scenario: Unrelated input identity is preserved

- **GIVEN** a retained fresh-retry payload contains non-tool-search items or tool-search fields other than the top-level `id`
- **WHEN** the retry payload is sanitized
- **THEN** those items and fields remain unchanged

### Requirement: Compact trimming preserves prioritised historical side effects

Oversized compact trimming MUST reserve bounded historical side-effect pairs before optional ordinary head/tail context, using downstream replay deduplication's classifier: code-mode `exec`/`collaboration` wrappers, lower-level spellings, and recognised parallel batches. Required state anchors/current item remain mandatory. Matching call/output pairs MUST stay together. If required state leaves no room, a pair MAY become a trim marker. Calls without non-empty `call_id` MUST NOT become anchors.


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
Public Responses endpoints MUST NOT return OpenAI-shaped `previous_response_not_found` errors. The API layer MUST rewrite any such error raised or collected below it as retryable `stream_incomplete` and remove the missing response id from the public payload.

#### Scenario: API layer receives an upstream previous-response miss
- **WHEN** a public `/responses`, `/v1/responses`, `/responses/compact`, or `/v1/responses/compact` handler receives an error with `code=previous_response_not_found`
- **OR** it receives `code=invalid_request_error` with `param=previous_response_id` and a message saying the previous response was not found
- **THEN** the response status is retryable
- **AND** the public error code is `stream_incomplete`
- **AND** the missing `previous_response_id` is not exposed in the response body

### Requirement: Public /v1 responses SSE stream emits only OpenAI Responses contract events
Streaming `POST /v1/responses` MUST emit only OpenAI Responses SSE contract event types (`response.*` and `error`). The service MUST drop vendor-internal events, including all `codex.*` types such as `codex.rate_limits`. Exempt `/backend-api/codex/*` routes MUST continue forwarding these events unchanged.

#### Scenario: Codex-internal rate-limit event is dropped before response.created
- **WHEN** the upstream Codex backend emits `codex.rate_limits` before `response.created` for a streaming `/v1/responses` request
- **THEN** the public stream MUST NOT contain the `codex.rate_limits` event
- **AND** the first event the public stream emits MUST be `response.created`

#### Scenario: Codex-internal events on the Codex CLI route are preserved
- **WHEN** the upstream emits `codex.rate_limits` for a `POST /backend-api/codex/responses` request
- **THEN** the response stream forwards the `codex.rate_limits` event to the Codex CLI client unchanged

### Requirement: Streamed /v1 responses terminal output is backfilled from item events
For streaming `POST /v1/responses`, the service MUST fill terminal `response.completed` or `response.incomplete` `output` that is missing or `[]` from earlier `response.output_item.done` events in that stream before yielding the terminal event. It MUST preserve `output_index` order and raw item payloads, and MUST forward existing non-empty terminal `output` unchanged.

#### Scenario: Terminal response.completed with empty output is backfilled from streamed items
- **GIVEN** the upstream emits `response.output_item.done` events with valid message or function-call items
- **WHEN** the upstream's terminal `response.completed` event carries `output: []`
- **THEN** the public stream's terminal `response.completed` event MUST carry the reconstructed `output` array, populated from the streamed `output_item.done` items in `output_index` order
- **AND** an OpenAI Python SDK consumer calling `stream.get_final_response().output` MUST receive the same populated list

#### Scenario: Terminal response.completed already carries output
- **WHEN** the upstream's terminal `response.completed` event already includes a non-empty `output` array
- **THEN** the public stream's terminal event MUST carry that `output` array unchanged

### Requirement: Public /v1 responses SSE stream starts with response.created
Streaming `POST /v1/responses` MUST emit `response.created` as its first OpenAI-contract event. If upstream's first standard `response.*` event has another type, the service MUST synthesize `response.created` from that event's `response` envelope and emit it first, preventing OpenAI Python SDK `responses.stream(...)` initialization `RuntimeError`.

#### Scenario: Upstream error stream that skips response.created is repaired
- **WHEN** the upstream's first standard event is `response.failed` (no preceding `response.created`)
- **THEN** the public stream MUST emit a synthesized `response.created` event derived from the failed event's `response` envelope before forwarding the `response.failed` event
- **AND** an OpenAI Python SDK consumer iterating the stream MUST NOT raise `RuntimeError` from the parser's initial-response check

#### Scenario: Normal stream is not double-emitted
- **WHEN** the upstream's first standard event is already `response.created`
- **THEN** the public stream MUST emit exactly one `response.created` event (no synthesized duplicate)

### Requirement: Upstream overload envelopes are classified as retryable transient failures

`classify_upstream_failure` MUST classify upstream envelopes with `code` `overloaded_error` or `server_is_overloaded` as `retryable_transient` regardless of HTTP status, including overloads streamed after HTTP 200.

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

Before any upstream connection, the service MUST validate `strict: true` function-tool schemas against OpenAI Structured Outputs (https://platform.openai.com/docs/guides/structured-outputs) and existing `enforce_strict_text_format` policy for `text.format.json_schema`. It MUST apply the recursive node constraints and native/coerced error-field contract below.

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

### Requirement: Strict function tool schemas enforce recursive node constraints

In `strict: true` function-tool schemas, every `object` node MUST set `additionalProperties: false`, every `properties` key MUST appear in `required`, and every node MUST have `type` (no empty `{}` schemas). These rules MUST apply recursively to objects, arrays, and `anyOf`/`oneOf`/`allOf` schemas.

#### Scenario: Nested strict schema nodes receive the same validation

- **WHEN** a strict function-tool schema nests an object in an array or combinator
- **THEN** that object requires `additionalProperties: false`, all property keys in `required`, and a `type`
- **AND** empty schema nodes are invalid

### Requirement: Strict function schema failures preserve native and coerced error fields

Strict function-schema violations MUST return `HTTP 400 invalid_request_error` with `error.code = "invalid_function_parameters"` and `error.message = "Invalid schema for function '<name>': In context=<path>, <reason>."`. `error.param` MUST be `"tools[<index>].parameters"` for native Responses requests or `"tools[<index>].function.parameters"` for chat completions routed through coercion.

#### Scenario: Coerced chat tool reports its original parameter path

- **WHEN** coercion detects an invalid strict function schema in chat-completions tool index 2
- **THEN** the response is HTTP 400 `invalid_request_error` with code `invalid_function_parameters`
- **AND** `error.param` is `tools[2].function.parameters`
- **AND** the message follows the specified function-name, context-path, and reason template

### Requirement: Same-response side-effect tool-call replays are suppressed

Only the first `response.output_item.done` per side-effect operation in a response SHALL pass (`exec_command`, `write_stdin`, `multi_tool_use.parallel`, `apply_patch_call`). `call_id` alone MUST NOT distinguish replays. Nested parallel matching ignores volatile `exec_command` wait/output fields (e.g. `yield_time_ms`, `max_output_tokens`), scopes `write_stdin` by `session_id`/`chars` and `wait_agent` by target set. Distinct operations, read-only calls and cross-response operations MUST pass.

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
If a Responses follow-up's required continuity state cannot be safely reconstructed, the service MUST return a retryable continuity error. It MUST NOT expose raw `previous_response_not_found` for bridge-local metadata loss or similar internal gaps.

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
Responses request logs MUST separately persist the operator-requested tier, upstream-reported actual tier when available, and effective pricing tier. `fast` MUST normalize to `priority` before forwarding or requested-tier storage. Actual-tier evidence, independent billing fallback, and continuation reconstruction MUST follow the tier requirements below.

#### Scenario: Upstream reports a downgraded actual tier
- **WHEN** a client sends a Responses request with `service_tier: "priority"`
- **AND** the upstream completion explicitly reports `service_tier: "default"`
- **THEN** the persisted request log records requested tier `priority`, actual tier `default`, and billable tier `default`

#### Scenario: Fast alias is logged as a priority request
- **WHEN** a client sends `service_tier: "fast"`
- **AND** the upstream completion explicitly reports `service_tier: "default"`
- **THEN** the persisted request log records requested tier `priority`, actual tier `default`, and billable tier `default`

#### Scenario: Upstream omits the actual tier
- **WHEN** a client requests `priority` and no upstream event reports a tier
- **THEN** actual tier is null and billable tier falls back to requested `priority`

#### Scenario: Initial auto does not replace terminal priority
- **WHEN** a continued response starts with created tier `auto` and finishes with explicit terminal tier `priority`
- **THEN** the folded completion and persisted actual tier are `priority`
- **AND** every upstream continuation request retains the requested tier

#### Scenario: Created-only tier remains accounting fallback
- **WHEN** a created response reports `default` and the completion omits `service_tier`
- **THEN** the completion does not inherit `service_tier`
- **AND** actual tier is null while the existing billable-tier fallback remains `default`

#### Scenario: Failed or interrupted stream does not prove a terminal tier
- **WHEN** a stream reports a created tier but fails, is cancelled, disconnects, or finishes incomplete
- **THEN** actual-tier evidence remains absent

### Requirement: Actual service tier requires explicit terminal evidence

Streaming `actual_service_tier` MUST come only from a nonblank explicit tier in `response.completed.response`. Created, in-progress, failed, incomplete, cancelled, or disconnected streams MUST NOT supply it. If completion omits it, actual-tier evidence MUST remain absent despite earlier tiers. Successful non-streaming compact responses MAY supply it directly.

#### Scenario: Nonterminal tier does not establish actual-tier evidence

- **WHEN** a stream reports a tier before completion but completion omits it
- **THEN** `actual_service_tier` remains absent

### Requirement: Billable tier fallback remains independent of actual-tier evidence

Billing MUST independently preserve its existing fallback: explicit terminal tier takes precedence, otherwise observed-event/request fallback remains available without populating `actual_service_tier`.

#### Scenario: Billing fallback does not become actual-tier evidence

- **WHEN** no terminal tier is present but an observed-event or requested tier is available
- **THEN** the existing billing fallback remains available
- **AND** it does not populate `actual_service_tier`

### Requirement: Continuation tier reconstruction preserves terminal absence

Continuation reconstruction MUST preserve final upstream terminal `service_tier`, including absence. It MUST NOT inherit a created-response tier when the terminal omits it. Synthesized incomplete responses MUST NOT claim a created-response tier as an upstream terminal tier.

#### Scenario: Synthesized incomplete response cannot inherit terminal evidence

- **WHEN** the proxy synthesizes an incomplete response after a created event with a tier
- **THEN** it does not claim that created-event tier as an upstream terminal tier

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

For Responses traffic, the service MUST recognize Cursor-style aliases appending `minimal`, `low`, `medium`, `high`, `xhigh`, `extra`, `fast`, `priority`, `reasoning`, or `thinking` to supported GPT-5 slugs. It MUST match longer qualified canonical slugs before shorter family prefixes. Unknown suffixes MUST leave the requested model unchanged.

#### Scenario: Qualified mini model alias normalizes reasoning

- **WHEN** a client sends a Responses request with `model: "gpt-5.4-mini-high"`
- **THEN** the forwarded upstream request uses `model: "gpt-5.4-mini"`
- **AND** the forwarded upstream request uses `reasoning.effort: "high"`

#### Scenario: Qualified codex model alias normalizes service tier

- **WHEN** a client sends a Responses request with `model: "gpt-5.3-codex-fast"`
- **THEN** the forwarded upstream request uses `model: "gpt-5.3-codex"`
- **AND** the forwarded upstream request uses `service_tier: "priority"`

### Requirement: OpenAI-compatible Responses payload sanitation removes provider-specific thinking aliases

Shared OpenAI-compatible Responses sanitation MUST normalize third-party thinking aliases into canonical `reasoning` before forwarding. It MUST NOT forward unknown provider-specific thinking controls unchanged to the upstream ChatGPT backend.

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
For OpenAI-style streaming `/v1/responses` and `/backend-api/codex/responses`, the service MUST emit renderable `response.output_text.delta` events when upstream supplies assistant text only in output items or terminal output. It MUST NOT duplicate deltas for an item that already emitted one.

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
The service MUST forward upstream tool-call deltas and output items when streaming and MUST include tool-call items in non-streaming final output.

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
Responses routing MUST prefer eligible accounts below the configured budget threshold over those above it. If none are below, the service MAY use pressured candidates.

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
Operators MUST be able to select streaming Codex/Responses upstream transport through dashboard settings. The resolved strategy MAY be `auto`, `http`, or `websocket`. `default` MUST defer to server configuration.

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
The service SHALL accept built-in Responses tools on `/backend-api/codex/responses` and `/v1/responses` without local rejection. It MAY normalize documented aliases, but model/tool compatibility validation MUST remain upstream.

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

The system SHALL accept upload-referencing `input_file` items with `file_id` in list- or string-form `input` on `/backend-api/codex/responses` and `/v1/responses`. It MUST forward them verbatim upstream. The same MUST apply to `/responses/compact`. The proxy MUST NOT raise `input_file.file_id is not supported` for these items.

#### Scenario: input_file with file_id is accepted in a /responses request

- **WHEN** a client posts a `/v1/responses` request whose `input` contains a `{"type": "input_file", "file_id": "file_abc"}` content item
- **THEN** the request validates and the upstream payload includes that content item unchanged

#### Scenario: input_file with file_id is accepted in a compact request

- **WHEN** a client posts a `/responses/compact` request whose `input` contains an `input_file` item with a `file_id`
- **THEN** the request validates and is forwarded to upstream verbatim

### Requirement: Responses requests with input_file.file_id route to the upload's account

For `input_file.file_id` references on `/v1/responses`, `/backend-api/codex/responses`, or `/responses/compact`, a live in-memory pin SHALL route to the account that registered the file via `POST /backend-api/files`. Explicit `prompt_cache_key`, session (`StickySessionKind.CODEX_SESSION`), turn-state, and `previous_response_id` affinity MUST retain precedence and existing semantics. Among referenced live pins, the newest MUST win, breaking ties lexicographically by `file_id`.

#### Scenario: file_id pin drives routing for an input_file response

- **GIVEN** a `POST /backend-api/files` registered `file_xyz` through `account_a`
- **WHEN** a `/v1/responses` request references `{"type": "input_file", "file_id": "file_xyz"}` and has no stronger affinity
- **THEN** the proxy MUST route the request to `account_a`

#### Scenario: prompt_cache_key overrides the file_id pin

- **GIVEN** a pinned `file_xyz -> account_a`
- **WHEN** a `/v1/responses` request references `file_xyz` AND sets an explicit `prompt_cache_key`
- **THEN** the proxy MUST follow the prompt-cache affinity for routing and MUST NOT use the file_id pin

### Requirement: File operation failover honors typed transport provenance

For `POST /backend-api/files` and `POST /backend-api/files/{file_id}/uploaded`, the proxy MUST preserve typed routed-transport failure phase, code, and replay eligibility through service failover. Proven typed pre-dispatch failures MUST use existing previsible unary account failover regardless of credential-safe message wording. Text MUST NOT grant typed failures replay eligibility. Untyped failures MUST retain message-based classification.

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

### Requirement: Unsafe file transport failures preserve account ownership

For file create/finalize operations, TLS verification, ambiguous request, response-body, and process-wide network failures MUST NOT cause cross-account replay. Process-wide network failures MUST keep `proxy_network_unavailable`. Finalize requests pinned to the registering account MUST NOT change accounts.

#### Scenario: Unsafe failure cannot override a file owner

- **WHEN** a pinned finalize request encounters a typed transport failure
- **THEN** it is not replayed through another account
- **AND** a process-wide network failure retains `proxy_network_unavailable`

### Requirement: File finalization transport failures do not fail over after a poll response

After any upstream `POST /files/{file_id}/uploaded` poll returns HTTP, later transport failures for that finalize request MUST NOT permit account failover or cross-account finalization. This applies to account-routed and direct transports. Existing `401` forced-refresh/reselection behavior MUST remain unchanged, and pinned finalize ownership MUST remain enforced.

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

### Requirement: Codex backend session_id preserves account affinity
Backend Codex Responses and compact requests MUST use a non-empty accepted session header as upstream account affinity: `session_id`, `x-codex-session-id`, then `x-codex-conversation-id` in priority order. Without a client-supplied `prompt_cache_key`, the service MUST derive and attach a stable one before forwarding upstream.

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
HTTP `/v1/responses` and `/backend-api/codex/responses` MUST reuse upstream websocket continuity by stable bridge key: explicit session/conversation header, else normalized `prompt_cache_key`. If the client omits that key, the service MUST derive it from existing OpenAI cache-affinity inputs. Bridging MUST preserve the HTTP/SSE contract, log `transport = "http"`, and isolate different keys.

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

Fresh durable HTTP bridges MUST preserve first client-unanchored full resends that resolve hard durable conversations, exactly match the stored input prefix, and have no client `previous_response_id`, reusable local bridge, or forwardable remote owner. Without response-owned bookkeeping, the suffix MUST retain completed assistant output before fresh user input or contain only complete direct call/output pairs exactly settling the durable prior-response tool-call manifest.

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

### Requirement: Durable tool-call manifests cover the complete response lifecycle

The durable manifest MUST include every observed supported direct `response.output_item.added` call, require one matching `response.output_item.done` with the same call ID and type, and reconcile terminal-output calls. Incomplete, conflicting, duplicated, malformed, or unsupported lifecycles MUST persist an unknown, not partial, manifest. Manifests MUST bind to the exact durable response ID. Readers MUST treat mismatches as unknown.

#### Scenario: Manifest binding mismatch invalidates the proof

- **WHEN** a durable manifest's response ID differs from the durable response being continued
- **THEN** readers treat the manifest as unknown rather than proving a safe direct tool-loop resend

### Requirement: Proven safe durable resends preserve original input and ownership

For proven safe fresh durable bridge resends, the service MUST send original input without `previous_response_id`, retaining the durable preferred account and hard affinity. It MUST NOT use account-neutral replay, trim the stored prefix before first send, or seed the local session with the old durable response so it re-injects the anchor before submission.

#### Scenario: Safe resend does not re-inject the old anchor

- **WHEN** a proven safe full resend starts a fresh durable bridge
- **THEN** the first send retains original input and durable account ownership without `previous_response_id`
- **AND** local session initialization does not re-inject the old response anchor

### Requirement: Unproven durable resends retain anchored continuation behavior

Resends omitting prior output or any durable call, containing incomplete/orphaned tool sequences, reusing stored-prefix call IDs, lacking a required known manifest, or otherwise failing proof MUST retain existing durable-anchor injection and verified-prefix trimming. Client anchors, owner-forward recovery, and live-session continuation MUST remain unchanged.

#### Scenario: Missing manifest preserves existing anchor injection

- **WHEN** a durable direct tool-loop resend requires a manifest but none is known
- **THEN** existing durable-anchor injection and verified-prefix trimming remain in effect

### Requirement: Responses account selection accounts for in-flight pressure

Responses usage-based routing MUST include persisted usage and immediate in-process pressure: in-flight response-create work, active streams, leased token/cost estimates, recent selection pressure, account health, and configured account-local caps. Selection and lease acquisition MUST be atomic relative to other in-process selections. The critical section MUST NOT perform database/network calls, sleeps, or other blocking I/O.

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

Responses account leases MUST release/settle idempotently on success, upstream/local-startup errors, bridge-submit failure, startup-probe conversion, non-stream collect completion, failover, downstream disconnect, cancellation, timeout, retry, pending teardown, and request-to-connection ownership replacement. A bounded stale watchdog MUST reclaim leases surviving unexpected task cancellation/exceptions and emit warning/metric evidence. Leases MUST NOT persist in the database.

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

Streaming `/v1/responses` MUST include SSE anti-buffering/cache headers for common front-door proxies and emit an early flushable SSE comment or event before upstream startup appears idle. Periodic keepalives MUST continue while awaiting upstream events. Heartbeat comments MUST preserve the public event contract: ignoring comments, OpenAI-contract events begin with `response.created`.

#### Scenario: Streaming response includes anti-buffering headers

- **WHEN** a client starts streaming `POST /v1/responses`
- **THEN** the response headers include SSE content type and anti-buffering/cache directives
- **AND** the headers are present before upstream response completion

#### Scenario: Early heartbeat precedes long upstream silence

- **WHEN** upstream startup takes longer than the heartbeat interval
- **THEN** the client receives a flushable SSE heartbeat before a front-door origin idle timeout would trigger
- **AND** the first OpenAI-contract event remains `response.created` when upstream accepts the request

### Requirement: Codex WebSocket top-level previous-response errors are masked
On Codex-native `/backend-api/codex/responses` WebSockets, the proxy MUST treat upstream `type: "error"` frames with top-level error fields and no nested `error` object as error envelopes. For `previous_response_not_found`, it MUST use existing fail-closed continuity handling and MUST NOT expose the raw code or missing response id downstream.

#### Scenario: ChatGPT backend emits top-level previous-response miss on Codex websocket
- **WHEN** a `/backend-api/codex/responses` WebSocket follow-up has `previous_response_id`
- **AND** the ChatGPT backend emits `{"type":"error","code":"previous_response_not_found","param":"previous_response_id",...}` without a nested `error` object
- **THEN** the downstream event is a retryable continuity failure such as `stream_incomplete`
- **AND** the downstream payload does not contain `previous_response_not_found`
- **AND** the downstream payload does not expose the missing previous response id

### Requirement: Equal idle and request-budget stream deadlines preserve idle classification
With equal upstream idle timeout and request budget, a started Responses body idle for that full window MUST time out as `stream_idle_timeout`, despite late scheduler observation. Classification MUST remain `upstream_request_timeout` if the budget is shorter than idle timeout, total timeout fires before response start, remaining next-read budget is shorter than a fresh idle window, or total timeout follows recent upstream body activity.

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
When the oldest of multiple pending upstream websocket or HTTP bridge turns reaches equal idle/request-budget deadlines, `stream_idle_timeout` alone MUST NOT fail all turns. The system MUST fail only turns whose own budget elapsed and keep younger turns queued until their own terminal event or timeout.

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

While awaiting upstream queue events, HTTP bridge Responses requests MUST emit downstream SSE liveness at `sse_keepalive_interval_seconds`. The first generated frame MUST wait until after the startup-error probe window, allowing local startup `ProxyResponseError` to return non-2xx HTTP. A generated frame MUST mark the stream started for HTTP-error propagation: later `response.failed` events are forwarded in-stream, not raised as startup errors.

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

### Requirement: HTTP bridge native liveness uses verified client identity

With a response id, HTTP bridge liveness MAY use `response.in_progress` for that id. Before one exists, verified native Codex clients on `/backend-api/codex/responses` MUST receive `codex.keepalive` JSON SSE events, even with payload-triggered OpenAI normalization. Native identity MUST use the existing native User-Agent or originator allowlist and MUST NOT come from continuity headers.

#### Scenario: Continuity headers do not establish native identity

- **WHEN** an HTTP bridge request supplies continuity headers without a verified native User-Agent or originator
- **THEN** those headers alone do not select native Codex liveness

### Requirement: HTTP bridge SDK liveness preserves public normalization policy

Explicit OpenAI SDK fingerprints, including `x-stainless-*` or OpenAI User-Agent, MUST take heartbeat precedence and receive comments. Public `/v1/responses` and other non-native OpenAI SDK streams MUST retain pre-`response.created` comment heartbeats. Public normalization MUST preserve comments and drop `codex.*` liveness. Heartbeat selection MUST NOT disable authentication, payload validation, event/fingerprint normalization, or routing policy.

#### Scenario: SDK heartbeat choice does not bypass request policy

- **WHEN** an explicit OpenAI SDK fingerprint selects comment liveness for an HTTP bridge request
- **THEN** authentication, payload validation, event and fingerprint normalization, and routing policy remain enabled

### Requirement: Codex WebSocket pre-created turns receive application heartbeats
On Codex-native `/backend-api/codex/responses` WebSockets, the proxy SHALL emit parseable Codex vendor heartbeats for pending `response.create` requests before upstream `response.created`. Heartbeats MUST be application text frames, resetting watchdogs that ignore protocol ping/pong. After upstream assigns a response id, the proxy MUST use the existing `response.in_progress` shape for that id.

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

For Codex or OpenAI-compatible Responses WebSockets, pre-visible upstream terminal `response.failed` or `error` with `error.code = "invalid_api_key"` or `error.type = "authentication_error"` MUST be treated as account-local auth state, not immediately surfaced. The proxy MUST preserve no-replay rules after downstream-visible output and for non-replayable continuations.

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

Before surfacing account-local compact auth failures, `/backend-api/codex/responses/compact` MUST recover upstream `401 invalid_api_key` or `401 token_invalidated` with one forced refresh and same-account retry. Another `401` MUST classify/log the failure, exclude the account for this request, and try another eligible account if available. Compact auth ownership and settlement protections below remain mandatory.

#### Scenario: Refreshed compact auth failure uses another account

- **GIVEN** at least two accounts are eligible for a compact request
- **AND** the selected account returns `401 invalid_api_key` for compact before and after a forced refresh
- **WHEN** another eligible account can complete the compact request
- **THEN** the downstream compact response succeeds from the second account
- **AND** the selected account is excluded from further attempts for that compact request

#### Scenario: Refreshed compact token invalidation uses another account

- **GIVEN** at least two accounts are eligible for a compact request
- **AND** the selected account returns `401 token_invalidated` for compact before and after a forced refresh
- **WHEN** another eligible account can complete the compact request
- **THEN** the downstream compact response succeeds from the second account
- **AND** the selected account is marked `reauth_required`
- **AND** the selected account is excluded from further attempts for that compact request

#### Scenario: Compact 401 is not a generic same-contract retry

- **WHEN** low-level compact transport receives HTTP 401 from upstream
- **THEN** the service-level auth refresh/failover path handles it
- **AND** the low-level compact transport does not mark it as a generic same-contract transport retry

#### Scenario: Permanent forced-refresh failure uses another account

- **GIVEN** at least two accounts are eligible for an account-neutral compact request
- **AND** the selected account returns an upstream authentication failure
- **WHEN** its forced refresh reports a permanent revoked-credential failure
- **THEN** the selected account is marked `reauth_required` and excluded
- **AND** the compact request succeeds from another eligible account when it completes
- **AND** the selected account's authentication error is not surfaced to the client

#### Scenario: Permanent forced-refresh failure preserves an account pin

- **GIVEN** a compact request is pinned to an account by file or continuity ownership
- **AND** that account returns an upstream authentication failure
- **WHEN** its forced refresh reports a permanent credential failure
- **THEN** the account is marked `reauth_required`
- **AND** the request is not sent to another account
- **AND** the terminal authentication error is surfaced after settlement

### Requirement: Permanent compact refresh failures require re-authentication and safe failover

If forced compact token refresh confirms permanent credential failure, the proxy MUST mark the selected account re-authentication-required, exclude it from the current compact request, and try another eligible account when ownership permits.

#### Scenario: Permanent refresh failure excludes the selected account

- **WHEN** forced compact refresh confirms permanently revoked credentials
- **THEN** the selected account is marked re-authentication-required and excluded from this compact request
- **AND** another eligible account is tried only when ownership permits

### Requirement: Compact auth recovery preserves account pins and terminal settlement

The proxy MUST NOT expose account-local compact `401` before exhausting eligible accounts or move file-/continuity-pinned compact requests across accounts. Without a safe replacement, terminal auth errors and settlement behavior MUST remain unchanged.

#### Scenario: No safe compact replacement preserves terminal settlement

- **WHEN** a compact authentication failure has no safe replacement account
- **THEN** the terminal auth error and existing settlement behavior are preserved
- **AND** file or continuity ownership is not bypassed

### Requirement: Pre-visible proxy auth failures fail over after forced refresh

Before downstream-visible output, repeated account-local auth failures MUST become per-request account failures. If a refreshed non-compact retry still returns upstream `401 invalid_api_key`, the proxy MUST classify/log the failure, exclude that account for this request, and try another eligible account if available. Existing no-replay rules after visible stream or websocket output MUST remain unchanged.

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

On `/backend-api/codex/responses` or bridge-backed Responses WebSockets, upstream `type: "error"` MUST use Codex classification: non-2xx `status`/`status_code` signals HTTP error. Detail MAY be nested `error` or top-level (`code`, `message`, `param`, `error_type`). Classification/rewrites MUST use supplied `error_type`, never discriminator `type`. `previous_response_not_found` MUST use established `stream_incomplete` recovery/rewrites without exposing raw code or missing id.

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
HTTP and websocket `/backend-api/codex/responses` request-create payloads MUST accept top-level `type: "image_generation"` tools. Shared validation and upstream forwarding MUST preserve these and all other tool entries, along with the existing public `/v1/*` built-in tool forwarding policy.

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

If local HTTP bridge startup waits prevent upstream work beyond the configured proxy admission wait timeout, the service MUST return terminal local overload, not keepalive-only `/v1/responses`, `/backend-api/codex/responses`, or compact streams.

#### Scenario: HTTP bridge startup wait stalls before first upstream event

- **WHEN** a streaming Responses request enters the HTTP responses bridge
- **AND** bridge startup is blocked by local bridge admission state before any upstream `response.*` event can be emitted
- **AND** the wait exceeds the configured proxy admission wait timeout
- **THEN** the request fails with a terminal error
- **AND** the error payload identifies local proxy overload with `error.code = "proxy_overloaded"`

### Requirement: Accept duplicated /v1/ prefix under /backend-api/codex
Before routing, the service MUST transparently alias `/backend-api/codex/v1/<rest>` with non-empty `<rest>` to the path without `/v1`, using the unchanged canonical handler. Aliasing MUST NOT apply to bare `/backend-api/codex/v1` or `/backend-api/codex`. Top-level `/v1/<rest>` routes remain unchanged.

#### Scenario: Misbehaving client requests duplicated prefix
- **WHEN** a client requests `GET /backend-api/codex/v1/models`
- **THEN** the response is identical to `GET /backend-api/codex/models`

#### Scenario: Canonical paths are unchanged
- **WHEN** a client requests `GET /backend-api/codex/models` or `GET /v1/models`
- **THEN** the request is routed to its existing handler without modification

### Requirement: Backend Responses endpoint accepts OpenAI-compatible request shapes
HTTP `/backend-api/codex/responses` SHALL accept `/v1/responses` request shapes, including string `input` and omitted/null `instructions`. It MUST normalize into the internal Responses model before forwarding, return `text/event-stream` Responses SSE events, and preserve backend Codex session/cache affinity.

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
Servers and clients of Codex-native `/backend-api/codex/responses` WebSockets MUST treat upstream `previous_response_id` as ephemeral optimization, not durable state. Stale-anchor failure during long-wait tool-output continuation MUST NOT end the user turn before one full-context retry without `previous_response_id`.

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
This OpenSpec change MUST define Codex-native WebSocket previous-response continuity, not ad hoc route/branch patches. Future behavior changes MUST update OpenSpec requirements before code.

#### Scenario: Previous-response fix changes behavior
- **WHEN** a patch changes routing, replay, masking, retry, or failure behavior for Codex-native WebSocket `previous_response_id`
- **THEN** the patch includes an OpenSpec delta or updates the active continuity source of truth
- **AND** direct `/backend-api/codex/responses` WebSocket tests or Codex client WebSocket tests cover the changed behavior

### Requirement: Direct WebSocket previous-response misses never leak raw upstream errors
For direct `/v1/responses` and `/backend-api/codex/responses` WebSockets depending on `previous_response_id`, the service MUST NOT send raw upstream `previous_response_not_found` payloads downstream.

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

If upstream websocket close/timeout interrupts an HTTP bridge request before `response.completed` and precreated replay fails to reconnect and resend, the service MUST terminally fail the pending request and retire the bridge session.

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

For classified local DNS/host-route failures with transport proof of no dispatch, Responses requests MUST retry on the same account with bounded backoff until success or existing budget expiry. Classified token-refresh network failures MUST receive this recovery only with typed proof the refresh POST was not dispatched. Recovery MUST NOT transfer account-owned continuation/file state to another account.

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

### Requirement: Network recovery remains within the original deadline

For pre-dispatch Responses network recovery, client rotation/construction, cleanup, and sleep MUST stay within the original monotonic deadline. Existing HTTP/SSE keepalives MUST remain active while the client waits.

#### Scenario: Recovery setup consumes the original request budget

- **WHEN** pre-dispatch network recovery rotates or constructs a client, cleans up, or sleeps
- **THEN** that work remains within the original monotonic deadline
- **AND** existing HTTP/SSE keepalives remain active while waiting

### Requirement: Uncertain-delivery network failures never replay transparently

Post-connect send/receive failures, response/body-read failures, and serialized terminal response events with uncertain upstream delivery MUST retain account-neutral network classification and MUST NOT replay transparently.

#### Scenario: Uncertain response-read failure remains account-neutral without replay

- **WHEN** a Responses network failure occurs during response-body reading with uncertain upstream delivery
- **THEN** the failure retains account-neutral network classification
- **AND** the proxy does not transparently replay the request

### Requirement: Native `/backend-api/codex` routes accept the Codex tool surface
Native `/backend-api/codex/responses` HTTP/websocket requests MUST accept Codex Desktop tools, including custom tools and built-ins such as `image_generation`, `file_search`, `code_interpreter`, and `computer_use_preview`. The service MUST normalize `web_search_preview` to `web_search` before forwarding. OpenAI-style `/v1/*` routes MUST reject unsupported built-ins with `invalid_request_error`.

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

With HTTP responses bridging enabled and runtime worker count above one, the service MUST NOT start plain Uvicorn workers sharing a bridge instance id. It MUST start one front listener and single-worker backends, each with a unique bridge id and advertised endpoint routing owner handoff to its local session map.

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

### Requirement: Pre-commit ambiguous websocket 403 failures fail over by account

Before a Responses path emits downstream bytes, events, or frames, ambiguous upstream websocket-connect `403` MUST be treated as account-scoped failure, not immediately surfaced. Retries MUST retain the upstream transport family. The service MUST NOT downgrade to HTTP solely because of that `403`.

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
If upstream websocket close or send rejection permits a pre-created Responses request to replay fresh, the service MUST record a transient upstream stream error against the failed account and exclude it from replay reconnect selection.

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

Upstream websocket handshakes built from inbound HTTP headers MUST exclude `accept`, `content-type`, hop-by-hop headers, `sec-websocket-*`, `accept-encoding`, and `cookie`, including HTTP bridge creation/reconnection. Service-set websocket protocol headers, such as the Responses websocket beta header, remain unaffected.

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

Codex-affinity compaction MUST preserve a selected upstream item's non-empty string `id` with its opaque `encrypted_content` in normalized output. The proxy MUST NOT invent or replace item IDs. The normalized item MUST match in direct Codex compact JSON and both terminal-trigger SSE locations. Public OpenAI-style compact behavior MUST remain unchanged.

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

Normalized Responses inline estimates reaching the effective model's conservative guard limit MUST return HTTP 400 code `context_length_exceeded`, type `invalid_request_error` before admission, account selection, or upstream connect. Opaque prior-response/conversation/file/image context of unknown total size MAY retain upstream handling. A single final top-level `compaction_trigger` MUST bypass HTTP stream/collect and websocket `response.create` guards. Malformed placement MUST NOT qualify.

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
Before replacing self-contained websocket full replay with injected `previous_response_id` and a sliced delta, the service MUST check reasoning consistency: every assistant `message` must have preceding `reasoning` within that delta. Reasoning without a following message and complete reasoning/message groups are consistent. Otherwise, the service MUST skip injection, forward the original full replay unchanged, and log a distinct skip reason.

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
If upstream rejects a websocket turn with `invalid_request_error` for missing required `reasoning` after proxy anchor injection, the service MUST reconnect and replay retained retry-safe self-contained full input without `previous_response_id` as a fresh turn. Without that body, it MUST return retryable continuity failure, not the raw error. Non-proxy-injected client anchors MUST NOT trigger this recovery and MUST receive the upstream error unchanged.

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

Direct Responses WebSocket requests MUST NOT replay on fresh upstream generations after successfully sending any finite integer `sequence_number` downstream for that request, except verified no-generation prewarm below. If upstream close would trigger replay, the proxy MUST settle the failed request without new-generation frames under the existing response id and close downstream with 1011.

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

### Requirement: Direct WebSocket terminal replay guards respect actual sequence exposure

After successful finite integer sequence emission for a direct Responses WebSocket request, terminal errors otherwise triggering quota, authentication, security-work, or equivalent replay MUST be finalized and surfaced without reconnecting. Suppressed frames and non-integer sequence sentinels MUST NOT alone disable otherwise-safe replay.

#### Scenario: Terminal error cannot restart an exposed generation

- **WHEN** a direct Responses WebSocket request emits a finite integer sequence and then receives a retryable terminal error
- **THEN** the proxy finalizes and surfaces that error without reconnecting

### Requirement: Verified no-generation prewarm is the sole numeric-sequence replay exception

The exception MUST require `request_kind = "prewarm"`, literal normalized `generate = false`, exactly one recorded `response.created`, no visible output, watermark `0`, one pending request, and existing one-shot eligibility. The proxy MUST suppress replayed `response.created` and MUST NOT renumber/synthesize sequences. A later finite integer replay sequence not exceeding the exposed watermark MUST settle as `stream_incomplete`, emit no synthetic terminal, and close downstream with 1011.

#### Scenario: Prewarm replay cannot regress the exposed watermark

- **WHEN** an eligible no-generation prewarm replays after exposing sequence `0`
- **THEN** replayed `response.created` is suppressed without renumbering or synthesizing sequences
- **AND** any later finite integer sequence at or below `0` settles `stream_incomplete`, emits no synthetic terminal, and closes downstream with 1011

### Requirement: Opaque-context detection tolerates arbitrary JSON

For Responses local input estimation, a mapping MUST qualify as opaque `input_file`/`input_image` only when `type` is that exact string. Any mapping with `file_id` MUST remain opaque. All other JSON, including schema fragments with object- or array-valued `type`, MUST be traversed recursively without error.

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

Before upstream websocket send, the service MUST measure serialized `response.create` size. Requests exceeding the upstream websocket budget MUST first slim only `input` before the latest user turn: historical inline images and oversized tool outputs MUST become textual omission notices preserving item sequence. Tool-output coverage and post-slimming rejection MUST follow the contracts below.

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

### Requirement: Historical slimming preserves tool-output identity and non-image content

Historical slimming MUST cover `function_call_output`, `custom_tool_call_output`, and `apply_patch_call_output`, including inline images nested in list- or mapping-valued `output` content parts. Those images MUST become image omission notices while non-image parts, item order, `call_id`, and `status` remain unchanged.

#### Scenario: Nested historical image replacement retains tool identity

- **WHEN** historical slimming encounters an inline image nested in a supported tool output's list or mapping
- **THEN** the image becomes an image omission notice
- **AND** non-image parts, item order, `call_id`, and `status` remain unchanged

### Requirement: Post-slimming websocket overflow returns a non-retryable input error

A `response.create` still exceeding the upstream websocket budget after historical slimming MUST fail locally with HTTP 400, not 413, and `error.code = "payload_too_large"`, `error.type = "invalid_request_error"`, `error.param = "input"`.

#### Scenario: Historical slimming cannot fit the websocket budget

- **WHEN** a serialized `response.create` remains over the upstream websocket budget after historical slimming
- **THEN** the proxy returns local HTTP 400 with code `payload_too_large`, type `invalid_request_error`, and param `input`
- **AND** it does not send the oversized request upstream or return HTTP 413

### Requirement: Responses Lite signaling enforces all-turns reasoning context

Canonical HTTP/per-request websocket client-metadata Lite signaling (body-derived, bridge-preserved, or continuity-trusted) MUST force exact `reasoning.context = "all_turns"` before serialization, creating missing/null reasoning and preserving all other members. Normalization MUST be idempotent, leave non-Lite shapes unchanged, and MUST NOT establish Lite/trust, remove signals, or reject otherwise-valid context mismatches. Invalid non-object reasoning keeps existing validation.

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

HTTP `/v1/responses` and `/backend-api/codex/responses`, including trailing slashes, MUST budget raw and decompressed bodies by the larger of `max_decompressed_body_bytes` and `max_decompressed_responses_body_bytes`. The Responses-specific default MUST remain 128 MiB. Trailing-slash routes MUST be hidden canonical-handler aliases, not redirects, preserving streamed admission, authorization, and routing.

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

### Requirement: Responses ingress overflow remains distinct from application overflow

Exceeding either Responses raw or decompressed ingress budget MUST return pre-parsing HTTP 413 with OpenAI `error.code = payload_too_large`, `error.type = invalid_request_error` before route logic or upstream forwarding. Requests within the 128 MiB ingress budget but oversized for upstream websocket after historical slimming MUST retain application-level HTTP 400 `payload_too_large` and `param = input`.

#### Scenario: Ingress rejection precedes application processing

- **WHEN** either raw or decompressed Responses ingress exceeds its budget
- **THEN** HTTP 413 `payload_too_large` / `invalid_request_error` is returned before parsing, route logic, or upstream forwarding
- **AND** the separate post-slimming application overflow contract remains HTTP 400 with `param = input`

### Requirement: Ordered owner-unavailable settlement preserves external errors

Ordered streaming Responses owner-unavailable settlement MUST preserve downstream and logged error envelopes using `previous_response_owner_unavailable`. Account-health recovery MAY retain the original upstream recovery code internally and MUST NOT expose raw stale-anchor identifiers.

#### Scenario: Ordered rewrite keeps the public and logged classifier

- **WHEN** a streaming `/v1/responses` failure is rewritten after ordered reservation settlement
- **THEN** the downstream error code is `previous_response_owner_unavailable`
- **AND** the request-log error code is `previous_response_owner_unavailable`
- **AND** no raw stale-anchor identifier is exposed

### Requirement: Suppressed duplicate side-effect replays receive a dedicated terminal failure

If upstream completes a turn whose replayed side-effecting call was suppressed, the proxy MUST emit terminal `response.failed` with `duplicate_tool_call_replay_suppressed` using the downstream response id. It MUST treat the request as non-success and MUST NOT penalize the account for this intentional suppression.

#### Scenario: Direct SSE reports the dedicated terminal

- **GIVEN** a direct SSE request suppresses a replayed side-effecting tool call
- **WHEN** the upstream emits `response.completed` for that replay
- **THEN** the client receives `response.failed` with code `duplicate_tool_call_replay_suppressed`
- **AND** the request log records `duplicate_tool_call_replay_suppressed`, not `stream_incomplete`

#### Scenario: HTTP bridge reports the dedicated terminal

- **GIVEN** an HTTP bridge request suppresses a replayed side-effecting tool call
- **WHEN** the upstream emits `response.completed` for that replay
- **THEN** the client receives `response.failed` with code `duplicate_tool_call_replay_suppressed`
- **AND** the request log records `duplicate_tool_call_replay_suppressed`

#### Scenario: WebSocket reports the dedicated terminal

- **GIVEN** a WebSocket request suppresses a replayed side-effecting tool call
- **WHEN** the upstream emits `response.completed` for that replay
- **THEN** the downstream terminal uses `duplicate_tool_call_replay_suppressed`
- **AND** the upstream account is not penalized for the intentionally suppressed replay
