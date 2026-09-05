## 1. Implementation

- [x] 1.1 Add `_shared_ssl_context` / `_reset_shared_ssl_context` in `http.py`.
- [x] 1.2 Use the shared context in `_build_http_client`.
- [x] 1.3 Clear the cache from `close_http_client`.
- [x] 1.4 Coordinate Codex/settings callsites with LoggingPorts.

## 2. Validation

- [ ] 2.1 Unit cache/reset/policy parity tests (parent).
- [ ] 2.2 Codex session/SOCKS reuse tests (LoggingPorts / parent).
