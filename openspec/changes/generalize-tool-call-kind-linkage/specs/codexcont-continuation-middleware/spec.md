## MODIFIED Requirements

### Requirement: Truncated Rounds Emitting Client Tool Calls Stop The Fold In Every Mode
codex-lb MUST stop a continuation fold — instead of opening another hidden
round — when the just-truncated round's buffered output contains a
client-answered tool call. A buffered item is a client-answered tool call
when its type is `function_call`, `custom_tool_call`, or `apply_patch_call`,
OR when it carries a non-empty `call_id` (any call kind whose output pairs on
`call_id`, e.g. `tool_search_call`). The rule SHALL apply uniformly in all
three fold modes: chained WebSocket turns, anchorless WebSocket turns, and
the HTTP pull engine. The stopped fold MUST flush the buffered output — tool
calls included — into the delivered downstream events and the reconstructed
terminal's `output`, so the client receives the calls it must answer.

#### Scenario: Truncated round with a call kind outside the enumerated set
- **WHEN** a chained WebSocket turn's round truncates on the continuation
  fingerprint and its buffered output contains a `tool_search_call` carrying
  a `call_id`
- **THEN** no hidden continuation round is opened
- **AND** the turn completes with the `tool_search_call` delivered to the
  client and `proxy_stopped_reason` set to `buffered_tool_calls`

### Requirement: Orphaned Tool-Output Errors Fail Closed
codex-lb MUST classify upstream tool-call linkage errors
(`type=invalid_request_error`, `param=input`) matching either invariant
message frame — `"No tool output found for <kind> call call_..."` or
`"No <kind> call found for <kind> output with call_id ..."` — for any call
kind wording (`function call`, `tool search call`, ...), as a
continuity-corruption condition, on both the WebSocket relay and the HTTP
bridge paths. Matching turns MUST NOT relay the raw upstream 400 downstream;
they MUST receive the fail-closed `stream_incomplete` rewrite so the client
retries with a self-contained full-history resend.

#### Scenario: Orphaned tool output on a follow-up turn is rewritten
- **WHEN** a WebSocket follow-up turn carrying `previous_response_id` receives
  the upstream error `"No tool call found for function call output with
  call_id call_X"`
- **THEN** the downstream client receives a `response.failed` terminal with
  code `stream_incomplete` and a `server_error` type
- **AND** the raw upstream message is not exposed downstream
- **AND** a `continuity_fail_closed` observation is recorded

#### Scenario: Tool-search linkage error is classified
- **WHEN** a WebSocket follow-up turn carrying `previous_response_id` receives
  the upstream error `"No tool output found for tool search call call_X"`
- **THEN** the downstream client receives the fail-closed `stream_incomplete`
  rewrite, not the raw 400
