# Share one outbound TLS verification context

## Why

Each outbound connector previously built a fresh `ssl.SSLContext` from the
system store plus certifi. That is CPU and RSS cost with no wire-policy
change.

Upstream microbench evidence (Soju06/codex-lb 862efac3; not this fork's
current proof): `create_codex_session()+close` 7.77 ms -> 0.055 ms per call
on py3.14.

## What Changes

- `http.py` exposes `_shared_ssl_context()` (`functools.cache` around the
  unchanged `_build_ssl_context`) and `_reset_shared_ssl_context()`.
- Shared client generations use the cached context; `close_http_client()`
  clears the cache.
- Codex session, SOCKS connector, and dashboard probe callsites are owned by
  LoggingPorts.

## Capabilities

### Modified Capabilities

- `outbound-http-clients`: connectors share one verification context without
  changing TLS policy.

## Impact

No verification-mode, hostname-check, protocol-floor, or CA-store policy
change. CA bundle updates on disk require process restart (or
`close_http_client()`), matching shared-client generations.
