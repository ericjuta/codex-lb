## 1. Middleware

- [x] 1.1 Add `ImageRouteStartedAtMiddleware` (pure ASGI) in `app/core/handlers/exceptions.py`.
- [x] 1.2 Register it via `app.add_middleware` inside `add_exception_handlers`, keeping the slot between app-version and trusted-proxy-headers.
- [x] 1.3 Remove the `@app.middleware("http")` registration.

## 2. Tests

- [x] 2.1 Assert image routes (all four paths, including `root_path`) receive a float start time via `scope["state"]` and `request.state`; other HTTP paths and WebSocket scopes are untouched.
- [x] 2.2 Assert pre-handler rejection observability consumes the ingress start time rather than the fallback.
- [x] 2.3 Assert forwarded ASGI messages are identical with and without the middleware (JSON and streaming).
- [x] 2.4 Pin that a mid-stream generator failure propagates without a synthetic terminal body chunk.

Omitted from this fork: upstream 2.1 (`create_app().user_middleware` contains no `BaseHTTPMiddleware`). This fork still registers other `@app.middleware("http")` entries.

## 3. Verification

### Upstream Verification (d771aa0f)
- [x] Upstream ran the middleware ordering tests, image-route observability integration tests, SSE unit tests, ruff, ty, the architecture check, and OpenSpec validation.
- [x] Upstream re-ran the BaseHTTPMiddleware vs pure-ASGI micro-benchmark and recorded the numbers in the PR body.

### Fork Verification
- [ ] 3.1 Run the image-route middleware tests, image-route observability integration tests, SSE unit tests, ruff, ty, the architecture check, and OpenSpec validation.
- [ ] 3.2 Re-run the BaseHTTPMiddleware vs pure-ASGI micro-benchmark.
