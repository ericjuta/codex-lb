# Release the Keep-Alive Timer on Connection Loss

## Why

Stock uvicorn cancels the HTTP/1.1 keep-alive timer in `connection_lost` only
when the peer closed cleanly (`exc is None`). Reverse proxies commonly purge
idle server-side connections with RST, which leaves the armed `TimerHandle`
pinning the protocol graph for the full keep-alive window.

Upstream incident evidence (Soju06/codex-lb 02b61d5b, 2026-09-03; not this
fork's current proof): a 2 GiB memcg OOM behind HAProxy with ~18k retained
protocol graphs over two hours at the former 7200 s default.

This fork does not carry the upstream h2c-tolerance protocol subclasses. The
port is timer-cleanup only: two minimal subclasses plus a selector that
preserves `auto` / `h11` / `httptools`.

## What Changes

- `KeepAliveHttpToolsProtocol` and `KeepAliveH11Protocol` cancel the
  keep-alive timer after stock `connection_lost` on every loss, including RST.
- `load_http_protocol_class(http)` preserves uvicorn's three HTTP modes.
- CLI `--timeout-keep-alive` default returns to 300 s (owned by LoggingPorts).

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `http-ingress-limits`: keep-alive timers must not outlive lost connections;
  idle window default is 300 s; HTTP implementation choice is preserved.

## Impact

`app/core/http_protocol.py`, `app/core/http_protocol_httptools.py`, CLI default
(LoggingPorts), focused protocol/timer tests. No native-egress, no h2c
behavior, no forwarded-byte change.
