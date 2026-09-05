# Context: release-keepalive-timer-on-connection-loss

## Purpose and scope

Cancel uvicorn's keep-alive timer on every HTTP connection loss. This change
does not add h2c upgrade tolerance, native egress, or load-balancer
decomposition.

## Decision

Stock uvicorn (`httptools_impl` / `h11_impl`) runs
`_unset_keepalive_if_required()` only inside `if exc is None`. An RST arrives
with `exc` set, so the `TimerHandle` keeps a bound method of the protocol
alive. The override calls `super().connection_lost(exc)` first, then cancels
the timer. The error path does not close the already force-closed transport.

This fork had no protocol subclasses. Adding the upstream h2c-tolerance
modules would expand architecture past the leak fix. The selector therefore
only wraps timer cleanup:

- `h11` -> `KeepAliveH11Protocol`
- `httptools` -> `KeepAliveHttpToolsProtocol` (ImportError if httptools missing)
- `auto` -> httptools subclass if importable, else h11

## Constraints

- TLS, upgrade handling, and forwarded bytes stay unchanged.
- CLI 300 s default/help is owned by LoggingPorts; this change only supplies
  `load_http_protocol_class`.

## Failure modes

- If the override is skipped, RST-closed connections retain the protocol for
  the full idle window while `server_state.connections` is empty.
- If `auto` stopped preferring httptools, operators who rely on httptools
  parsing would silently fall back to h11.

## Example

A client completes `GET /echo` and closes with `SO_LINGER(0)`. The server
observes `ConnectionResetError`, `timeout_keep_alive_task` is cancelled, and
the protocol is collectable without waiting for the idle window.

## Upstream provenance (not this fork's proof)

Upstream 02b61d5b recorded 300/300 retained protocols after RST before the
fix and 0/300 after, on asyncio 3.14 and uvloop 0.22. Local verification is
parent-owned and unchecked here.
