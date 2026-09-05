## ADDED Requirements

### Requirement: Image-route start-time middleware relays responses in the request task

The image-route start-time middleware MUST be a pure ASGI middleware that
invokes the downstream application in the same task and forwards response
messages directly. It MUST NOT be registered via Starlette
`BaseHTTPMiddleware` (including `@app.middleware("http")`). Response bodies
forwarded on success paths MUST be byte-identical to the downstream
application's output.

#### Scenario: Streaming body is forwarded unchanged

- **WHEN** a route returns a streaming response through the image-route start-time middleware
- **THEN** the sequence of ASGI response messages, including headers, body bytes, and `more_body` flags, is identical to the sequence emitted without the middleware

#### Scenario: Mid-stream failure propagates without a synthetic terminator

- **WHEN** a response body generator raises after at least one body chunk has been sent
- **THEN** the exception propagates to the ASGI server
- **AND** the stack does not emit an additional `http.response.body` message with `more_body=false` before propagating
