# Context: release-routed-upstream-stream-responses

## Purpose and scope

Release routed upstream streaming responses when the consumer stops before EOF
so aiohttp connections are not finalized by GC. Native-egress transports are
out of scope for this fork.

## Decision

`release_codex_response` (LoggingPorts) tries `release`, then `close`, then
`aclose`, awaiting only when the result is awaitable. The routed branch of
`_stream_via_http_attempt` runs that helper in `finally` before closing an
owned `CodexClient`. Nested generators from `stream_responses` down to
`_iter_sse_events` use `contextlib.aclosing` so consumer `aclose()` and
cancellation reach teardown synchronously.

Continuation folding is unique to this fork. Each continuation round wraps
`_stream_responses_with_session` in `aclosing` so round teardown still
releases the response. `codex_continuation.py` is unchanged.

## Constraints

- Cancellation MUST propagate; release MUST NOT swallow `CancelledError`.
- Forwarded bytes, error mapping, and retry classification stay unchanged.
- TLS verification policy is unchanged (separate shared-context change).

## Failure modes

- Missing `aclosing` leaves teardown to the asyncgen finalizer, so
  `Unclosed connection` still appears after GC.
- Releasing after client close can still leak the acquired connection.

## Example

A routed stream yields `response.completed` while upstream holds the
keep-alive tunnel. The consumer stops. Order is `release` then client
`close`; `response.closed` is true and `response.connection` is `None`.

## Upstream provenance (not this fork's proof)

Upstream 8afe0679 reported 30/30 unclosed-connection events before the fix
and 0/30 after on a repro harness. Local verification is parent-owned.
