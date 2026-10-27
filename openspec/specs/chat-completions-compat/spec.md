# Chat Completions Compatibility

## Purpose

Ensure `/v1/chat/completions` behavior matches OpenAI Chat Completions expectations by mapping to Responses semantics and preserving streaming and error envelopes.
## Requirements
### Requirement: Validate Chat Completions requests

The service MUST accept JSON POST requests to `/v1/chat/completions` and validate required fields per OpenAI Chat Completions expectations. Requests MUST include `model` and either a non-empty `messages` array of objects or a Responses-shaped `input` payload. Invalid payloads MUST return a 4xx OpenAI error envelope.

#### Scenario: Responses-shaped chat payload accepted

- **WHEN** the client sends `{ "model": "gpt-5.2", "input": [{"role":"user","content":[{"type":"input_text","text":"hi"}]}] }`
- **THEN** the service accepts the request and forwards it as a Responses payload without requiring `messages`

#### Scenario: Invalid messages payload

- **WHEN** the client sends an empty `messages` array without `input`, or sends non-object message items
- **THEN** the service returns a 4xx response with an OpenAI error envelope describing the invalid parameter

#### Scenario: Minimal valid chat request
- **WHEN** the client sends `{ "model": "gpt-4.1", "messages": [{"role":"user","content":"hi"}] }`
- **THEN** the service accepts the request and begins a response (streaming or non-streaming based on `stream`)
### Requirement: Enforce message content type rules
`system` and `developer` messages MUST contain only text. `user` messages MAY contain text, image, or file parts per OpenAI chat spec. Unsupported content types MUST return an OpenAI error envelope.

#### Scenario: Non-text system message
- **WHEN** a `system` or `developer` message includes a non-text content part
- **THEN** the service returns a 4xx response with an OpenAI error envelope indicating an invalid message content type

#### Scenario: User message with mixed content
- **WHEN** a `user` message includes a mix of text and image parts
- **THEN** the service accepts the request and forwards the content parts in order

### Requirement: Map chat requests to Responses wire format

The service MUST merge `system`/`developer` content into Responses `instructions` and forward other messages as `input`. For `response_format.type = "json_object"`, it MUST instead preserve `system`/`developer` messages and roles in `input`. Tool definitions MUST use the Responses tool schema. `tool_choice`, `reasoning_effort`, and `response_format` MUST be mapped consistently. Unsupported fields MUST not be silently ignored if they change behavior.

#### Scenario: System message normalization
- **WHEN** the client sends a `system` message followed by a `user` message
- **AND** the request does not use `response_format.type = "json_object"`
- **THEN** the service maps the system content to `instructions` and the user message to `input`

#### Scenario: JSON object response format preserves instruction-role messages
- **WHEN** the client sends `response_format: {"type":"json_object"}` with a `system` or `developer` message that instructs JSON output
- **THEN** the mapped Responses payload keeps that message in `input` with its original role
- **AND** the mapped `instructions` value does not contain that message content

#### Scenario: Tool choice values
- **WHEN** the client sets `tool_choice` to `none`, `auto`, or `required`
- **THEN** the service forwards the value consistently in the mapped Responses request

### Requirement: Preserve service_tier in Chat Completions mapping
The service MUST preserve any Chat Completions `service_tier` field in the internal Responses payload.

#### Scenario: Chat request includes fast-mode tier
- **WHEN** a client sends a valid Chat Completions request with `service_tier: "priority"`
- **THEN** the mapped Responses payload forwarded upstream includes `service_tier: "priority"`

### Requirement: Allow web_search tools in Chat Completions

Chat Completions MUST accept `web_search` and normalize `web_search_preview` to it. Non-empty `messages` MUST reject other built-in types (file_search, code_interpreter, computer_use, computer_use_preview, image_generation) with an OpenAI invalid_request_error. Responses-shaped chat payloads using `input` with absent or empty `messages` MUST preserve Responses tool definitions and `tool_choice`, including built-in tools accepted by `/v1/responses`.

#### Scenario: unsupported built-in tool rejected for chat messages

- **WHEN** the client sends `tools=[{"type":"image_generation"}]`
- **AND** the request includes a non-empty `messages` array
- **THEN** the service returns a 4xx OpenAI invalid_request_error indicating the unsupported tool type

#### Scenario: Responses-shaped built-in tool preserved

- **WHEN** the client sends a `/v1/chat/completions` payload with `input`, `messages` absent or empty, `tools=[{"type":"image_generation"}]`, and `tool_choice={"type":"image_generation"}`
- **THEN** the mapped Responses request preserves the `image_generation` tool and `tool_choice`

#### Scenario: web_search_preview tool normalized in mapping
- **WHEN** the client sends `tools=[{"type":"web_search_preview"}]`
- **THEN** the mapped Responses request includes a tool with type `web_search`
### Requirement: Reject file_id in Chat Completions
The service MUST reject chat `file` content parts that include `file_id` and return a 4xx OpenAI invalid_request_error with message "Invalid request payload".

#### Scenario: file_id rejected in chat file part
- **WHEN** a user message includes `{ "type": "file", "file": {"file_id":"file_123"} }`
- **THEN** the service returns a 4xx OpenAI invalid_request_error with message "Invalid request payload" and param `messages`

### Requirement: Streaming chat completions are emitted as chat.completion.chunk
When `stream=true`, the service MUST respond with `text/event-stream` and emit `chat.completion.chunk` payloads. The first chunk MUST include the `assistant` role, tool call deltas MUST be streamed when present, and the stream MUST terminate with `data: [DONE]`.

#### Scenario: Streaming content and termination
- **WHEN** the upstream emits text deltas and completes
- **THEN** the service emits `chat.completion.chunk` deltas with an initial role and ends with `data: [DONE]`

#### Scenario: Stream usage chunk
- **WHEN** the client sets `stream_options: { "include_usage": true }`
- **THEN** the stream includes a final chunk with a `usage` field and empty `choices` before `data: [DONE]`

### Requirement: Non-streaming chat completions return a full chat.completion object
When `stream` is `false` or omitted, the service MUST return a single `chat.completion` JSON object containing `id`, `model`, `choices`, and `usage` when available. If tool calls are present, the message MUST include `tool_calls` and the `finish_reason` MUST be `tool_calls`.

#### Scenario: Non-streaming tool call response
- **WHEN** the upstream indicates a tool call sequence
- **THEN** the returned `chat.completion` includes `tool_calls` and a `finish_reason` of `tool_calls`

### Requirement: response_format mapping
The service MUST map any `response_format` to Responses `text.format`. For `json_schema`, it MUST validate the schema payload and return a 4xx OpenAI error envelope if `json_schema` is missing.

#### Scenario: JSON schema response format
- **WHEN** the client sends `response_format: {"type":"json_schema","json_schema":{...}}`
- **THEN** the service maps to `text.format` and preserves schema fields

#### Scenario: Missing json_schema
- **WHEN** the client sends `response_format` with `type: "json_schema"` but omits `json_schema`
- **THEN** the service returns a 4xx response with an OpenAI error envelope

#### Scenario: Invalid json_schema name
- **WHEN** the client provides a `json_schema.name` outside the allowed pattern or length
- **THEN** the service returns a 4xx response with an OpenAI error envelope indicating the invalid name

### Requirement: Large image inputs are handled per OpenAI limits
Per OpenAI chat input limits, the service MUST drop image inputs larger than 8MB from `user` messages.

#### Scenario: Oversized image input
- **WHEN** a `user` message includes an image input larger than 8MB
- **THEN** the service drops the image input and proceeds with remaining parts

### Requirement: Reject input_audio in Chat Completions
The service MUST reject chat user content parts with type `input_audio` and return a 4xx OpenAI invalid_request_error.

#### Scenario: input_audio rejected
- **WHEN** a user message includes `{ "type": "input_audio", "input_audio": {"data":"...","format":"wav"} }`
- **THEN** the service returns a 4xx OpenAI invalid_request_error indicating audio input is unsupported

### Requirement: Error mapping for chat requests
For upstream failures or invalid requests, the service MUST return an OpenAI error envelope for non-streaming responses or an error chunk followed by `data: [DONE]` for streaming responses. Error `code`, `type`, and `message` MUST be preserved or normalized into stable values.

#### Scenario: Streaming error
- **WHEN** the upstream returns a failure during streaming
- **THEN** the service emits an error chunk and terminates the stream with `data: [DONE]`

### Requirement: Drop unknown message-object fields during coercion

Chat-to-Responses `input` message coercion MUST emit only `role` and `content` for `user`/`assistant` messages without tool_calls and assistant message-content halves with tool_calls. It MUST omit `name`, standard fields without a Responses input-item equivalent and arbitrary keys (including `_`-prefixed keys). This applies only to message items. Tool-call decomposition (`FunctionCallInputItem`) and tool-message conversion (`FunctionCallOutputInputItem`) retain their field selection.

#### Scenario: Standard `name` field is dropped

- **WHEN** a client sends `{ "model": "...", "messages": [{ "role": "user", "content": "hi", "name": "alice" }] }`
- **THEN** the mapped Responses payload's `input` contains exactly `[{ "role": "user", "content": [{"type": "input_text", "text": "hi"}] }]` with no `name` key on the input item

#### Scenario: Arbitrary client-internal keys are dropped

- **WHEN** a client sends a message carrying client-internal bookkeeping keys, e.g. `{ "role": "user", "content": "hi", "_client_marker": true, "extra": 1 }`
- **THEN** the mapped Responses payload's `input` item for that message contains exactly `role` + `content` and no other keys

#### Scenario: Assistant message with tool_calls drops unknown keys on the message half

- **WHEN** a client sends an assistant message that has both `content` and `tool_calls`, with extra keys on the message object (`name`, `_client_marker`, etc.)
- **THEN** the message-content half of the decomposed input items is `{ "role": "assistant", "content": [...] }` with no `name` / `_client_marker` keys, and the tool-call half remains a well-formed `function_call` input item

#### Scenario: No regression for clean messages

- **WHEN** a client sends a message that already carries only `role` and `content` (the most common case)
- **THEN** the mapped Responses payload's `input` item for that message is byte-equivalent to the previous behavior

### Requirement: `_normalize_chat_tools` preserves the function tool strict flag

Chat Completions `tools[]` normalization MUST preserve each `function` tool's nested `function.strict` as Responses `strict`. After coercion, `to_responses_request()` invokes `enforce_strict_function_tools_format`, preserving responses-api-compat strict-schema pre-validation and endpoint consistency for equivalent payloads. `strict` does not apply to non-function tools (`web_search`, etc.); their behavior is unchanged.

#### Scenario: Chat tool with strict=true and compliant schema is forwarded with strict preserved

- **WHEN** a client sends `tools: [{"type": "function", "function": {"name": "f", "parameters": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"], "additionalProperties": false}, "strict": true}}]`
- **THEN** the coerced Responses tool item is `{"type": "function", "name": "f", "description": null, "parameters": {...}, "strict": true}`, and the upstream request is accepted (`200`)

#### Scenario: Chat tool with strict=true and violating schema is rejected with 400

- **WHEN** a client sends a chat tool with `strict: true` but `parameters.additionalProperties` is missing or `true`
- **THEN** the proxy returns `HTTP 400` with `error.code = "invalid_function_parameters"` and `error.param = "tools[<index>].function.parameters"`, without any upstream connection being opened

#### Scenario: Responses-shaped chat payload with flat strict tool is rejected with 400

- **WHEN** a client sends a Responses-shaped payload through `/v1/chat/completions` using `input` and a flat Responses function tool with `strict: true` but a violating `parameters` schema
- **THEN** the proxy returns `HTTP 400` with `error.code = "invalid_function_parameters"` and `error.param = "tools[<index>].parameters"`, without any upstream connection being opened

#### Scenario: Chat tool with strict=false or omitted is forwarded with strict preserved (or absent)

- **WHEN** a client sends a chat tool without a `strict` key (or with `strict: false`)
- **THEN** the coerced Responses tool item has no `strict` key (or `strict: false`) accordingly, and no strict-mode pre-validation is run for that tool

#### Scenario: Built-in tool types are unaffected

- **WHEN** a client sends `tools: [{"type": "web_search"}]`
- **THEN** the coerced Responses tool item is unchanged (no `strict` field considered), matching pre-fix behavior

### Requirement: Chat Completions normalizes provider-specific thinking aliases

The service MUST normalize Chat Completions provider-specific reasoning controls commonly used by non-OpenAI SDKs into internal Responses `reasoning` before forwarding upstream. It MUST NOT forward the original fields unchanged.

#### Scenario: Qwen-style enable_thinking is normalized

- **WHEN** a client calls `/v1/chat/completions` with `enable_thinking: true`
- **AND** no explicit `reasoning` or `reasoning_effort` override is present
- **THEN** the mapped Responses payload includes `reasoning.effort: "medium"`
- **AND** the forwarded upstream payload does not include `enable_thinking`

#### Scenario: Anthropic-style thinking object is normalized

- **WHEN** a client calls `/v1/chat/completions` with `thinking: {"type":"enabled","budget_tokens":2048}`
- **AND** no explicit `reasoning` or `reasoning_effort` override is present
- **THEN** the mapped Responses payload includes `reasoning.effort: "medium"`
- **AND** the forwarded upstream payload does not include `thinking`

### Requirement: Preserve tool strictness semantics in Responses-shaped chat payloads

Flat Responses function tools in Responses-shaped chat payloads MUST undergo strict-mode validation. Invalid strict schemas MUST be rejected before contacting upstream, with rejection details reporting the flat tool schema param path.

#### Scenario: Responses-shaped chat payload with flat strict tool is rejected with 400

- **WHEN** a client sends a Responses-shaped payload through `/v1/chat/completions` using `input` and a flat Responses function tool with
  `strict: true` but a violating `parameters` schema
- **THEN** the proxy returns `HTTP 400` with `error.code = "invalid_function_parameters"` and `error.param = "tools[<index>].parameters"`
- **AND** no upstream connection is opened
