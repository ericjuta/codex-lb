## Context

WebSocket Responses admission reserves an account stream lease on `_WebSocketRequestState` before an upstream reader adopts it. The connection also keeps the currently active lease in a local `account_lease` variable. A new request can be admitted while the prior reader is still unwinding, and disconnect cleanup can remove pending request state before its reserved lease is transferred. Both paths currently allow the final reference to an acquired lease to disappear while `inflight_streams` remains elevated.

## Goals / Non-Goals

**Goals:**

- Preserve exactly-one release semantics across the request-state-to-connection ownership transfer.
- Release request-owned leases during pending-request failure cleanup.
- Keep account stream pressure accurate after disconnects and rapid sequential requests.

**Non-Goals:**

- Change account selection, stream-cap calculation, or stale-lease watchdog policy.
- Change external WebSocket events, error envelopes, or retry behavior.
- Add persistence or configuration.

## Decisions

### Release the connection lease before adopting the request lease

The response-create path will call the existing connection-level release helper before assigning the pending request's `websocket_stream_lease` to `account_lease`. Reusing the helper preserves its nulling and release behavior and makes the ownership order explicit: old connection owner releases, new request owner transfers, request field clears.

An alternative was to rely on the prior upstream reader's finalizer. That is insufficient because the next response-create can reach the transfer point before the reader finishes, overwriting the only connection-local reference.

### Drain request-owned leases in pending-request cleanup

`_fail_pending_websocket_requests` will release a non-null `websocket_stream_lease` through the load balancer and clear the field before publishing the terminal event. This cleanup owns leases that never reached the connection-level variable.

An alternative was to leave these leases to stale reclamation. That keeps healthy account capacity artificially occupied until a watchdog deadline and makes normal disconnect cleanup depend on exceptional recovery machinery.

## Risks / Trade-offs

- **Risk: the same lease is released by two cleanup paths.** The ownership transfer and cleanup paths clear their source field immediately, while the existing release operation is idempotent.
- **Risk: release failure interrupts pending-request cleanup.** The change uses the same awaited release contract as other lease terminal paths, preserving existing error visibility instead of silently leaking pressure.

## Migration Plan

No migration is required. The change is process-local and takes effect when the proxy runtime is updated. Rollback restores the previous cleanup behavior without data conversion.

## Open Questions

None.
