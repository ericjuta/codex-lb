# http-ingress-limits Specification

## Purpose

Bound raw HTTP request ingress so oversized or streaming bodies are rejected against the applicable budget before downstream parsing.
## Requirements
### Requirement: Raw HTTP request ingress is bounded incrementally

The service MUST enforce the applicable request-body budget against actual raw bytes received for each guarded HTTP request. It MUST reject the request before exposing a chunk that would make the cumulative raw body exceed the budget, and it MUST NOT prebuffer the complete body solely to enforce this limit.

#### Scenario: Declared oversized body is rejected before downstream parsing

- **WHEN** a guarded HTTP request declares a valid `Content-Length` greater than its applicable budget
- **THEN** the service returns HTTP 413 without invoking downstream request-body parsing

#### Scenario: Chunked body crosses the budget

- **WHEN** a guarded HTTP request has no usable `Content-Length` and its received chunks cumulatively exceed the applicable budget
- **THEN** the service returns HTTP 413
- **AND** the chunk that crosses the budget is not exposed to downstream body parsing

#### Scenario: Exact-boundary body is accepted by the ingress guard

- **WHEN** a guarded HTTP request's actual raw body size equals its applicable budget
- **THEN** the raw ingress guard allows the complete body to continue downstream

#### Scenario: Client disconnect remains a disconnect

- **WHEN** the ASGI server reports `http.disconnect` while a guarded body is being received
- **THEN** the ingress guard propagates the disconnect without converting it into an HTTP 413 response

### Requirement: HTTP ingress reuses existing budgets

The service MUST use `max_decompressed_body_bytes` as the general raw and decompressed HTTP request-body budget. When an owning route capability defines a larger budget from an existing route-specific setting, the ingress guard MUST use that route budget. The HTTP ingress guard MUST NOT add another setting or change existing defaults.

Route-specific budget and error-envelope selection MUST use the application-relative route path after removing any matching ASGI `root_path` prefix.

Requests declaring `multipart/form-data` without `Content-Encoding` MUST remain outside this generic whole-body guard. Multipart requests carrying `Content-Encoding` MUST remain guarded. The service MUST NOT treat the client-declared multipart media type as a trusted security boundary.

#### Scenario: Another HTTP path uses the general budget

- **WHEN** a guarded request targets any other HTTP path
- **THEN** its raw and decompressed HTTP ingress budget is `max_decompressed_body_bytes`

#### Scenario: Declared unencoded multipart remains unaffected

- **WHEN** a request declares media type `multipart/form-data` and has no `Content-Encoding`
- **THEN** the generic raw whole-body guard does not reject it based on these budgets

#### Scenario: Encoded multipart remains guarded

- **WHEN** a `multipart/form-data` request carries a `Content-Encoding` header
- **THEN** the service applies both the raw and decompressed budget checks

#### Scenario: Mounted Responses route keeps its route-specific policy

- **GIVEN** the service is mounted under a non-empty ASGI `root_path`
- **WHEN** the request scope path includes that prefix and targets `/v1/responses` relative to the application
- **THEN** the service applies the Responses-specific ingress budget
- **AND** any ingress failure uses the OpenAI-compatible error envelope

### Requirement: Encoded HTTP bodies are bounded before and after decompression

For request bodies using `gzip`, `deflate`, `zstd`, `identity`, or supported stacked `Content-Encoding` values, the service MUST enforce the applicable budget independently against the encoded raw body and every intermediate and final decoded representation. The service MUST remove stacked encodings in reverse header/application order. Unsupported encodings or malformed compressed bodies MUST fail with HTTP 400.

#### Scenario: Encoded raw body exceeds the budget

- **WHEN** an encoded request's raw bytes exceed the applicable budget before decompression
- **THEN** the service returns HTTP 413 before attempting to hold an unbounded encoded body

#### Scenario: Expanded body exceeds the budget

- **WHEN** an encoded request is within the raw budget but expands beyond the applicable decompressed budget
- **THEN** the service returns HTTP 413

#### Scenario: Supported stacked encoding remains compatible

- **WHEN** a request uses a valid supported stack of `gzip`, `deflate`, `zstd`, or `identity` encodings and both representations fit the budget
- **THEN** the service decodes the body in reverse header/application order, caps every intermediate representation, and continues request handling

#### Scenario: Invalid compression is rejected

- **WHEN** a request uses an unsupported content encoding or carries malformed compressed bytes
- **THEN** the service returns HTTP 400 without invoking route logic

### Requirement: HTTP ingress failures use the path-family error envelope

Ingress failures on `/v1/*`, `/backend-api/*`, `/api/codex/*`, and `/internal/bridge/*` MUST use an OpenAI-compatible error envelope with `type = invalid_request_error`. Equivalent paths MUST be classified after the existing outer path canonicalization. Other ingress paths MUST retain the dashboard-compatible error envelope. Oversized requests MUST use `code = payload_too_large`; malformed or unsupported compression MUST use `code = invalid_request_error` on OpenAI paths and `code = invalid_request` on other paths.

#### Scenario: OpenAI path rejects an oversized body

- **WHEN** a raw or decompressed request body on an OpenAI-compatible proxy path exceeds its budget
- **THEN** the service returns HTTP 413
- **AND** the response has OpenAI error `code = payload_too_large` and `type = invalid_request_error`

#### Scenario: OpenAI path rejects invalid compression

- **WHEN** a request on an OpenAI-compatible proxy path uses unsupported or malformed compression
- **THEN** the service returns HTTP 400
- **AND** the response has OpenAI error `code = invalid_request_error` and `type = invalid_request_error`

#### Scenario: Dashboard settings path rejects an oversized body

- **WHEN** a raw or decompressed request body on `/api/settings` exceeds its budget
- **THEN** the service returns HTTP 413
- **AND** the response has dashboard error `code = payload_too_large`

#### Scenario: Dashboard settings path rejects invalid compression

- **WHEN** a request on `/api/settings` uses unsupported or malformed compression
- **THEN** the service returns HTTP 400
- **AND** the response has dashboard error `code = invalid_request`

#### Scenario: Duplicated Codex alias is classified after canonicalization

- **WHEN** an ingress failure targets `/backend-api/codex/v1/responses/`
- **THEN** the service applies the same Responses budget and OpenAI-compatible envelope as `/backend-api/codex/responses/`

### Requirement: Ingress admission preserves endpoint authorization

The HTTP ingress guard MUST NOT authenticate callers or replace, bypass, or relocate existing dashboard, proxy API-key, ChatGPT-identity, or internal-bridge authorization. Requests that reach dependency resolution MUST continue through the endpoint's existing authorization path. Existing FastAPI parsing order remains unchanged, so ingress rejection or syntactically invalid typed bodies can fail before router-level authorization.

#### Scenario: Admitted unauthenticated request still reaches proxy authorization

- **WHEN** a syntactically valid under-limit request without required credentials targets an API-key-protected proxy route
- **THEN** the ingress guard allows normal routing to continue
- **AND** the existing proxy authorization rejects the request with its established authentication response

#### Scenario: Declared oversized request fails before authorization

- **WHEN** a request declares a body larger than its ingress budget
- **THEN** the service returns the deterministic ingress 413 without invoking router-level authorization

### Requirement: Keep-alive timers do not outlive lost connections

The server MUST release the per-connection keep-alive timer whenever an HTTP connection is lost, regardless of whether the peer closed it cleanly or the loss was reported with an error (connection reset, timeout, or any other transport error). No per-connection server state (protocol, transport wrapper, request cycle, or request scope) MAY remain reachable from the event loop solely because a keep-alive timer is still armed for a connection that no longer exists. Clean-close teardown and the timer's idle-close behavior on intact connections MUST be unchanged, and the server MUST NOT close the transport again on the error path.

#### Scenario: Peer resets an idle keep-alive connection after a response

- **WHEN** a client completes an HTTP/1.1 request on a keep-alive connection and then closes the connection abnormally so the server observes a connection-reset error rather than end-of-stream
- **THEN** the server cancels the connection's keep-alive timer immediately
- **AND** the connection's protocol state becomes garbage-collectable without waiting for the keep-alive window to elapse

#### Scenario: Clean close is unchanged

- **WHEN** a client completes a request and closes the connection cleanly
- **THEN** the server closes the transport and cancels the keep-alive timer as before
- **AND** the connection's protocol state becomes garbage-collectable

#### Scenario: Idle intact connection is still closed by the timer

- **WHEN** a keep-alive connection stays open and idle for the configured keep-alive window
- **THEN** the server closes the connection when the timer fires

### Requirement: HTTP protocol selection preserves auto, h11, and httptools

The server MUST honor the existing `--http` / `UVICORN_HTTP` choices `auto`, `h11`, and `httptools` while applying keep-alive timer cleanup. Explicit `h11` MUST select the h11 timer-cleanup subclass. Explicit `httptools` MUST select the httptools timer-cleanup subclass and MUST fail if httptools cannot be imported. `auto` MUST prefer the httptools timer-cleanup subclass when httptools is importable and MUST fall back to the h11 timer-cleanup subclass otherwise. Protocol selection MUST NOT add h2c or other upgrade-offer behavior.

#### Scenario: Explicit h11 mode

- **WHEN** the server starts with `--http h11`
- **THEN** inbound HTTP/1.1 connections use the h11 keep-alive timer-cleanup subclass
- **AND** the keep-alive timer is still released on connection loss

#### Scenario: Explicit httptools mode

- **WHEN** the server starts with `--http httptools` and httptools is installed
- **THEN** inbound HTTP/1.1 connections use the httptools keep-alive timer-cleanup subclass
- **AND** the keep-alive timer is still released on connection loss

#### Scenario: Explicit httptools fails when unavailable

- **WHEN** the server starts with `--http httptools` and httptools cannot be imported
- **THEN** startup fails
- **AND** no h2c or other upgrade-offer behavior is added

#### Scenario: Auto prefers httptools when available

- **WHEN** the server starts with `--http auto` and httptools is importable
- **THEN** inbound HTTP/1.1 connections use the httptools keep-alive timer-cleanup subclass
- **AND** protocol selection does not add h2c or other upgrade-offer behavior

### Requirement: Idle keep-alive window is bounded and configurable

The server MUST close an idle HTTP/1.1 keep-alive connection after a configurable window. The default window MUST be 300 seconds. The window MUST be configurable via the `--timeout-keep-alive` CLI flag and the `UVICORN_TIMEOUT_KEEP_ALIVE` environment variable, with the CLI flag taking precedence, and an invalid (non-integer) value MUST fail startup with a clear error.

#### Scenario: Default keep-alive window

- **WHEN** the server starts without `--timeout-keep-alive` or `UVICORN_TIMEOUT_KEEP_ALIVE`
- **THEN** idle keep-alive connections are closed after 300 seconds

#### Scenario: Operator overrides the keep-alive window

- **WHEN** the operator starts the server with `--timeout-keep-alive <seconds>` or sets `UVICORN_TIMEOUT_KEEP_ALIVE=<seconds>`
- **THEN** idle keep-alive connections are closed after the configured window

#### Scenario: Invalid keep-alive window fails startup

- **WHEN** `UVICORN_TIMEOUT_KEEP_ALIVE` or `--timeout-keep-alive` is not an integer
- **THEN** startup fails with an error naming the flag and variable

### Requirement: Image-route start-time middleware relays responses in the request task

The image-route start-time middleware MUST be a pure ASGI middleware that invokes the downstream application in the same task and forwards response messages directly. It MUST NOT be registered via Starlette `BaseHTTPMiddleware` (including `@app.middleware("http")`). Response bodies forwarded on success paths MUST be byte-identical to the downstream application's output. This requirement applies only to the image-route start-time middleware and MUST NOT require every other HTTP middleware to be pure ASGI.

#### Scenario: Streaming body is forwarded unchanged

- **WHEN** a route returns a streaming response through the image-route start-time middleware
- **THEN** the sequence of ASGI response messages, including headers, body bytes, and `more_body` flags, is identical to the sequence emitted without the middleware

#### Scenario: Mid-stream failure propagates without a synthetic terminator

- **WHEN** a response body generator raises after at least one body chunk has been sent
- **THEN** the exception propagates to the ASGI server
- **AND** the stack does not emit an additional `http.response.body` message with `more_body=false` before propagating
