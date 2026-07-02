## ADDED Requirements

### Requirement: Folded WebSocket Turns Preserve Next-Turn Chaining
codex-lb MUST, when a WebSocket Responses turn is folded across hidden
continuation rounds, keep the downstream-visible response id stable (the
visible round's id) and map that visible id to the final hidden round's upstream
response id so that a follow-up turn referencing the visible id in
`previous_response_id` is forwarded upstream with the final round's id. Both
the visible id and the final round's upstream id MUST be registered in the
previous-response owner index for follow-up account routing.

#### Scenario: Follow-up after a folded tool-call turn chains the final round
- **WHEN** a folded WebSocket turn's hidden round emits a `function_call` and
  the client's next turn on the same session sends the folded (visible)
  response id as `previous_response_id` with the matching
  `function_call_output`
- **THEN** codex-lb rewrites `previous_response_id` to the final hidden
  round's upstream response id before forwarding upstream
- **AND** the upstream request resolves the tool call without an
  `invalid_request_error`

#### Scenario: Downstream id remains stable on folded turns
- **WHEN** a WebSocket turn folds one or more hidden continuation rounds
- **THEN** the downstream `response.completed` carries the same response id as
  the turn's downstream `response.created`

### Requirement: Chained Hidden WebSocket Rounds Chain The Previous Round
codex-lb MUST send a hidden WebSocket continuation round for a chained turn
with `previous_response_id` set to the just-completed round's own response id,
and an input consisting only of that round's replayed reasoning items plus the
continuation marker. A chained turn's incremental input resolves solely
against upstream stored context, and the upstream invalidates an anchor once a
response has chained off it — the original client anchor is consumed by the
visible round and MUST NOT be reused, and the incremental input MUST NOT be
replayed (it already lives in the visible round's stored context). Turns
without an anchor MUST continue to use the anchorless full-input replay.
When a chained turn's truncated round emitted a client-answered tool call
(`function_call`, `custom_tool_call`, or `apply_patch_call`), codex-lb MUST
NOT open a hidden round (the anchored context would hold an unanswered call);
it MUST stop the fold and deliver the buffered output, including the tool
call, to the client.

#### Scenario: Chained turn's hidden round chains the visible round
- **WHEN** a WebSocket turn carrying `previous_response_id` and incremental
  tool-output input truncates on the continuation fingerprint
- **THEN** the hidden continuation round is sent upstream with
  `previous_response_id` equal to the visible round's response id and input
  containing only the visible round's reasoning items and the continuation
  marker
- **AND** the folded turn completes without a stale-anchor or orphaned
  tool-output error

#### Scenario: Truncated chained round with a tool call stops the fold
- **WHEN** a chained WebSocket turn's round truncates on the continuation
  fingerprint and its buffered output contains a `function_call`
- **THEN** no hidden continuation round is opened
- **AND** the turn completes with the tool call delivered to the client

### Requirement: Folded Turns Track Only Delivered Calls As Interruptible
codex-lb MUST, when a folded WebSocket turn completes, limit the turn's
pending (interruptible) function-call tracking to calls present in the folded
terminal's delivered output. Under the unified stop rule no fold mode
discards a buffered client tool call — a truncated round emitting one stops
the fold and delivers it — so this prune is a defense-in-depth invariant:
should a regression reintroduce a discarded call, the client never received
it and the final round's stored upstream context does not contain it, so
interrupted-tool-output injection MUST NOT synthesize an output for any call
absent from the delivered terminal output on a follow-up turn.

#### Scenario: Undelivered call is not treated as interrupted
- **WHEN** a folded turn's terminal output omits a `function_call` observed
  mid-turn (a discard regression) and the client answers a different
  delivered `function_call` on the next turn
- **THEN** the follow-up request forwarded upstream contains only the client's
  `function_call_output`
- **AND** no synthetic interrupted output is injected for the undelivered call

### Requirement: Orphaned Tool-Output Errors Fail Closed
codex-lb MUST classify the upstream error message
`"No tool call found for function call output with call_id ..."`
(`type=invalid_request_error`, `param=input`) as a continuity-corruption
condition equivalent to the existing missing-tool-output classification, on
both the WebSocket relay and the HTTP bridge paths. Matching turns MUST NOT
relay the raw upstream 400 downstream; they MUST receive the fail-closed
`stream_incomplete` rewrite so the client retries with a self-contained
full-history resend.

#### Scenario: Orphaned tool output on a follow-up turn is rewritten
- **WHEN** a WebSocket follow-up turn carrying `previous_response_id` receives
  the upstream error `"No tool call found for function call output with
  call_id call_X"`
- **THEN** the downstream client receives a `response.failed` terminal with
  code `stream_incomplete` and a `server_error` type
- **AND** the raw upstream message is not exposed downstream
- **AND** a `continuity_fail_closed` observation is recorded
