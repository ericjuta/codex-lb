## Why

Routed HTTP streams request the response unbuffered and stop before body EOF.
Closing the per-stream client without releasing the response leaves aiohttp
connections for cyclic GC, which logs `Unclosed connection`.

Upstream production evidence (Soju06/codex-lb 8afe0679, 2026-09-03; not this
fork's current proof): 44–1350 unclosed-connection lines per hour.

This fork has no native-egress helper. Release is duck-typed over aiohttp
`release()`, optional `close()`, `aclose()`, and no-op objects.

## What Changes

- Routed HTTP streaming releases the raw response before closing the owned
  client on every exit, including cancellation.
- Nested HTTP stream generators are consumed under `contextlib.aclosing`.
- SOCKS-owned responses remain LoggingPorts' `release_codex_response` wrappers.

## Impact

- Affected specs: `outbound-http-clients`
- Affected code: `app/core/clients/proxy.py` (this change), `app/core/clients/codex.py` (LoggingPorts)
- No native-egress additions.
