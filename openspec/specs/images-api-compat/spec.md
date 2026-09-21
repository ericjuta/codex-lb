# images-api-compat Specification

## Purpose
Define the OpenAI-compatible Images API adapter that exposes public `gpt-image-*`
requests while routing through the existing Responses `image_generation` tool
pipeline.
## Requirements
### Requirement: OpenAI-compatible image generation endpoint

The system SHALL expose `POST /v1/images/generations` and accept the OpenAI Images API request shape (`model`, `prompt`, `n`, `size`, `quality`, `background`, `output_format`, `output_compression`, `moderation`, `partial_images`, `stream`, `user`). The endpoint MUST require `model` to start with `gpt-image-` and MUST treat `gpt-image-2` as the default if unspecified. The endpoint MUST NOT expose the internal "host" Responses model used to invoke the built-in `image_generation` tool.

#### Scenario: Compatible image generation request returns a JSON envelope

- **WHEN** a client sends `POST /v1/images/generations` with `model=gpt-image-2`, a non-empty `prompt`, and no `stream`
- **THEN** the service returns 200 with a JSON body of shape `{created, data: [{b64_json, revised_prompt}], usage}` containing exactly one entry

#### Scenario: Unsupported model is rejected

- **WHEN** a client sends `POST /v1/images/generations` with `model` not starting with `gpt-image-`
- **THEN** the service returns 400 with OpenAI `invalid_request_error` and `param: model`

#### Scenario: Per-model parameter rules are enforced for gpt-image-2

- **WHEN** a client sends `gpt-image-2` with `background=transparent` or `input_fidelity=low|high`, or with `size` violating the gpt-image-2 size constraints (max edge ≤ 3840 px, both edges multiples of 16, ratio ≤ 3:1, total pixels in [655_360, 8_294_400])
- **THEN** the service returns 400 with OpenAI `invalid_request_error` describing the rejected parameter

#### Scenario: Per-model parameter rules are enforced for legacy gpt-image models

- **WHEN** a client sends `gpt-image-1.5`, `gpt-image-1`, or `gpt-image-1-mini` with `size` outside `{1024x1024, 1536x1024, 1024x1536, auto}`
- **THEN** the service returns 400 with OpenAI `invalid_request_error` and `param: size`

#### Scenario: Multi-image requests are rejected until upstream support arrives

- **WHEN** a client sends `/v1/images/generations` or `/v1/images/edits` with `n > 1`
- **THEN** the service returns 400 with OpenAI `invalid_request_error` and `param: n`, with a message that explains the upstream `image_generation` tool does not yet support multi-image responses
- **AND** no settings override SHALL raise the accepted request `n` above 1 until codex-lb implements client-side fan-out or upstream exposes first-class multi-image support

#### Scenario: Missing model defaults to images_default_model

- **WHEN** a client sends `/v1/images/generations` or `/v1/images/edits` without `model`
- **THEN** the service uses `images_default_model` (default `gpt-image-2`) as the publicly-effective model for validation, request log accounting, and the internal `image_generation` tool config

### Requirement: OpenAI-compatible image edit endpoint

The system SHALL expose `POST /v1/images/edits` and accept the OpenAI Images Edits multipart shape (`image` repeatable file part, optional `mask`, plus `model`, `prompt`, `n`, `size`, `quality`, `background`, `output_format`, `output_compression`, `partial_images`, `stream`, `user`). The endpoint MUST apply the same model gating and parameter rules as `/v1/images/generations`. The endpoint MUST forward `image[]` and `mask` parts as `input_image` content (base64 data URLs) inside the internal Responses request.

#### Scenario: Compatible image edit request returns a JSON envelope

- **WHEN** a client sends multipart `POST /v1/images/edits` with at least one `image` file part, `model=gpt-image-2`, and a non-empty `prompt`
- **THEN** the service returns 200 with a JSON body of shape `{created, data: [{b64_json, revised_prompt}], usage}`

#### Scenario: Unsupported variations endpoint is rejected

- **WHEN** a client sends `POST /v1/images/variations`
- **THEN** the service returns 404 with OpenAI `not_found_error` and a message indicating that variations are not supported

### Requirement: Image generation is implemented as a Responses tool adapter

The system SHALL implement `/v1/images/generations` and `/v1/images/edits` by issuing an internal `/v1/responses` request whose `tools` array includes `{"type": "image_generation", ...}` and whose `input` is constructed to deterministically force a single `image_generation` tool call. The system MUST route that internal request through the existing proxy account-selection, sticky session, retry, and authentication pipeline. The system MUST NOT introduce a new `chatgpt-token → openai-api-key` token-exchange path solely to support these endpoints.

#### Scenario: Internal Responses call uses existing routing

- **WHEN** any `/v1/images/*` request is processed
- **THEN** account selection, sticky-session affinity, API-key validation, and request budgeting use the same code paths as `/v1/responses`

#### Scenario: Multipart edits become input_image content

- **WHEN** an edit request includes `image` and optional `mask` multipart parts
- **THEN** each binary part is encoded as a `data:` URL and inserted as `input_image` content in the internal Responses input

### Requirement: Image routes select a code-owned Responses host model

The system SHALL select the internal Responses host for both
`POST /v1/images/generations` and `POST /v1/images/edits` from the ordered
candidates `gpt-5.6-luna`, then `gpt-5.5`. A candidate SHALL qualify only when
the existing model registry reports non-empty plan visibility and does not mark
that candidate suppressed. If neither candidate qualifies, the system SHALL
select `gpt-5.6-luna` as the default host.

The system MUST NOT expose an `images_host_model` setting or use operator
configuration to override this selection. The system MUST preserve
`images_default_model` and the public `gpt-image-2` default. Host selection MUST
NOT change public image-model policy, accounting, or request-log identity.
Catalog visibility MUST NOT grant account entitlement or bypass existing
account routing, authentication, suppression, or retry behavior.

#### Scenario: Both image routes prefer visible Luna over the old host

- **GIVEN** the registry reports non-empty plan visibility for both candidates and neither is suppressed
- **AND** the upstream accepts image requests hosted by Luna but rejects those hosted by `gpt-5.5`
- **WHEN** a client submits a valid generation request or multipart edit with public model `gpt-image-2`
- **THEN** the internal Responses model is `gpt-5.6-luna`
- **AND** the client receives the successful public image response without exposing the host model

#### Scenario: Hidden Luna falls back to visible GPT-5.5

- **GIVEN** Luna has no registry plan visibility and `gpt-5.5` has non-empty plan visibility without suppression
- **WHEN** a client submits a valid image generation or edit request
- **THEN** the internal Responses host is `gpt-5.5`

#### Scenario: Suppressed Luna is not selected ahead of visible GPT-5.5

- **GIVEN** Luna is suppressed, even if it has registry plan visibility
- **AND** `gpt-5.5` has non-empty plan visibility without suppression
- **WHEN** a client submits a valid image generation or edit request
- **THEN** the internal Responses host is `gpt-5.5`

#### Scenario: Neither candidate qualifies

- **GIVEN** neither candidate has non-empty registry plan visibility without suppression
- **WHEN** a client submits a valid image generation or edit request
- **THEN** the internal Responses host defaults to `gpt-5.6-luna`
- **AND** existing account routing still determines whether any account can serve that host

#### Scenario: Public model identity remains independent of the host

- **WHEN** a valid image generation or edit request omits its public model
- **THEN** it uses the unchanged `images_default_model` setting, whose default is `gpt-image-2`
- **AND** the image tool configuration, API-key policy, accounting, and request logs use the effective public image model rather than the selected Responses host

### Requirement: Image generation streaming uses canonical OpenAI Images events

When a client requests `stream=true` on `/v1/images/generations` or `/v1/images/edits`, the system SHALL translate upstream Responses SSE events into the OpenAI Images streaming format. The system MUST emit `image_generation.partial_image` for each upstream `response.image_generation_call.partial_image` and an `image_generation.completed` event for *every* `image_generation_call` ResponseItem the upstream surfaces, in arrival order, when the trailing `response.completed` arrives. The `usage` field MUST be attached only to the final `image_generation.completed` event so multi-image responses match the OpenAI Images streaming shape. The system MUST NOT forward Responses-specific events (`response.created`, `response.in_progress`, `response.image_generation_call.in_progress`, `response.image_generation_call.generating`, reasoning/content events) to the client. The system MUST also surface upstream errors that occur before the first SSE chunk as a structured OpenAI error envelope rather than a broken/truncated stream body.

#### Scenario: Partial images are forwarded with stable field names

- **WHEN** the upstream stream emits `response.image_generation_call.partial_image` with `partial_image_b64` and `partial_image_index`
- **THEN** the client receives `image_generation.partial_image` with `b64_json` set to `partial_image_b64`, the same `partial_image_index`, and the upstream `size`, `quality`, `background`, and `output_format`

#### Scenario: Final image completes the stream

- **WHEN** the upstream stream emits `response.output_item.done` with `item.type == "image_generation_call"` and a non-empty `result`
- **THEN** the client receives `image_generation.completed` with `b64_json`, `revised_prompt`, `size`, `quality`, `background`, and `output_format`, followed by a terminating `[DONE]`-equivalent event

#### Scenario: Upstream image generation failure becomes a single error event

- **WHEN** the upstream stream surfaces `response.failed` or an `image_generation_call` with `status == "failed"`
- **THEN** the client receives a single `error` event using an OpenAI error envelope and the SSE stream is closed cleanly

### Requirement: Image routes participate in usage accounting and policy

The system SHALL apply API-key allowed-model policy and model-scoped usage limits to `/v1/images/*` using the publicly-requested `gpt-image-*` value as the effective model. The system SHALL record the publicly-requested `gpt-image-*` value (not the internal host model) in the request log's `model` column once the upstream response id becomes known.

#### Scenario: API key allowed-model policy blocks gpt-image-2

- **WHEN** an API key's `allowed_models` list does not include `gpt-image-2`
- **THEN** requests to `/v1/images/generations` or `/v1/images/edits` with `model=gpt-image-2` return 403 `model_not_allowed`

#### Scenario: Request log surfaces the publicly requested image model

- **WHEN** an `/v1/images/*` request completes successfully against an internal host Responses model (for example `gpt-5.5`)
- **THEN** the resulting `request_logs` row has `model` equal to the publicly requested value (for example `gpt-image-2`) so dashboards and usage views surface the user-visible model rather than the internal host model

### Requirement: Image routes expose bounded operational observability

The system SHALL emit structured route-completion logs and Prometheus metrics for `/v1/images/generations` and `/v1/images/edits`. Observability labels MUST be bounded to route, effective public model, stream flag, HTTP status, and outcome, and MUST NOT include prompts, image bytes, file names, access tokens, or raw upstream payloads. The duration start time MUST be captured at HTTP ingress, before authentication, body admission, or handler execution, by a pure ASGI middleware that stores it in the request scope state; pre-handler rejections MUST measure duration from that ingress start time.

#### Scenario: Successful image request records completion telemetry

- **WHEN** an `/v1/images/generations` or `/v1/images/edits` request completes successfully
- **THEN** the service emits an `images_route_complete` log line with the public image route, public model, stream flag, status, outcome, and duration
- **AND** increments `codex_lb_image_requests_total` and observes `codex_lb_image_request_duration_seconds` with the same bounded labels

#### Scenario: Failed image request records completion telemetry

- **WHEN** an image request is rejected by validation or mapped from an upstream/image-generation error
- **THEN** the service emits the same bounded `images_route_complete` fields with a non-success outcome
- **AND** increments the image request counter and duration histogram without logging prompt or binary image content

#### Scenario: Pre-handler rejection measures duration from ingress

- **WHEN** an image route request is rejected before its handler runs, for example because of an oversized multipart upload or a missing API key
- **THEN** the recorded duration uses the start time stamped into the request scope state at HTTP ingress
- **AND** non-image HTTP paths and WebSocket scopes receive no such stamp
