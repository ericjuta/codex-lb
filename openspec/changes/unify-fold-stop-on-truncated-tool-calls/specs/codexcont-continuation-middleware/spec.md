## ADDED Requirements

### Requirement: Truncated Rounds Emitting Client Tool Calls Stop The Fold In Every Mode
codex-lb MUST stop a continuation fold — instead of opening another hidden
round — when the just-truncated round's buffered output contains a
client-answered tool call (`function_call`, `custom_tool_call`, or
`apply_patch_call`). The rule SHALL apply uniformly in all three fold modes:
chained WebSocket turns, anchorless WebSocket turns, and the HTTP pull
engine. The stopped fold MUST flush the buffered output — tool calls
included — into the delivered downstream events and the reconstructed
terminal's `output`, so the client receives the calls it must answer. No
fold mode SHALL discard a buffered client tool call: a chained hidden round
would anchor a context holding an unanswered call (the upstream rejects it),
and an anchorless or HTTP full-history replay would silently drop actionable
output and re-think, risking duplicate side-effect tool calls.

#### Scenario: Anchorless WebSocket turn stops and delivers the tool call
- **WHEN** a WebSocket turn without `previous_response_id` truncates on the
  continuation fingerprint and its buffered output contains a `function_call`
- **THEN** no hidden continuation round is opened
- **AND** the flushed downstream events and the reconstructed terminal's
  `output` contain the `function_call`, delivered exactly once

#### Scenario: HTTP pull fold stops and delivers the tool call
- **WHEN** an HTTP Responses stream folded by the pull engine truncates on
  the continuation fingerprint and the round's buffered output contains a
  `function_call`
- **THEN** no hidden continuation round is opened upstream
- **AND** the delivered stream ends with a `response.completed` terminal
  whose `output` contains the `function_call`

### Requirement: Buffered-Tool-Call Stops Carry An Overriding Stopped Reason
codex-lb MUST stamp `metadata.proxy_stopped_reason = "buffered_tool_calls"`
on the reconstructed terminal whenever a fold stops because the truncated
round's buffered output contains a client-answered tool call, in every fold
mode. The reason MUST override the generic stopped-reason derivation — it
MUST NOT be mislabeled by the derivation's `tier_out_of_window` fallback —
and the buffered-tool-call check MUST be evaluated only for rounds that
would otherwise continue, so rounds that do not hit the continuation
fingerprint keep their tool-call terminals unchanged with no stopped reason.

#### Scenario: HTTP fold stop reports buffered_tool_calls
- **WHEN** the HTTP pull engine stops a fold because the truncated round
  buffered a `function_call`
- **THEN** the reconstructed terminal carries
  `metadata.proxy_stopped_reason = "buffered_tool_calls"` and not
  `"tier_out_of_window"`

#### Scenario: Anchorless WebSocket fold stop reports buffered_tool_calls
- **WHEN** an anchorless WebSocket turn's fold stops because the truncated
  round buffered a `function_call`
- **THEN** the reconstructed terminal carries
  `metadata.proxy_stopped_reason = "buffered_tool_calls"`

#### Scenario: Ordinary tool-call terminal carries no stopped reason
- **WHEN** a round completes with a `function_call` but its reasoning-token
  count does not match the truncation fingerprint
- **THEN** the terminal is delivered without a `proxy_stopped_reason`
