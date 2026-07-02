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

### Requirement: Hidden WebSocket Rounds Preserve The Chained Anchor
codex-lb MUST send hidden WebSocket continuation rounds with the visible
round's `previous_response_id` anchor when the visible round was chained. A
chained turn's input is incremental (e.g. only `function_call_output` items)
and resolves solely against the anchor's stored context; hidden rounds
re-branch off the same anchor with the accumulated replay tail appended.
Turns without an anchor MUST be sent unchanged (no anchor is introduced).

#### Scenario: Chained turn's hidden round keeps the anchor
- **WHEN** a WebSocket turn carrying `previous_response_id` and incremental
  tool-output input truncates on the continuation fingerprint
- **THEN** the hidden continuation round is sent upstream with the same
  `previous_response_id` and the original input plus the replayed reasoning
  and continuation marker
- **AND** the folded turn completes without an orphaned tool-output error

### Requirement: Folded Turns Track Only Delivered Calls As Interruptible
codex-lb MUST, when a folded WebSocket turn completes, limit the turn's
pending (interruptible) function-call tracking to calls present in the folded
terminal's delivered output. Calls buffered in truncated rounds are discarded
by the fold — the client never receives them and the final round's stored
upstream context does not contain them — so interrupted-tool-output injection
MUST NOT synthesize outputs for them on a follow-up turn.

#### Scenario: Discarded truncated-round call is not injected
- **WHEN** a truncated round emits a `function_call` that the fold discards
  and the final hidden round emits a different `function_call` that the client
  answers on the next turn
- **THEN** the follow-up request forwarded upstream contains only the client's
  `function_call_output`
- **AND** no synthetic interrupted output is injected for the discarded call

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
