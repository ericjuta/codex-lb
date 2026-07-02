# codexcont-continuation-middleware Specification

## Purpose

Defeat upstream reasoning-token truncation (`truncation_step * n - 2`) on Codex
Responses streams by running hidden continuation rounds on the already-selected
upstream and folding them into one coherent downstream response, on both the
HTTP pull path and the WebSocket push path, without breaking next-turn
chaining, tool-call delivery, usage settlement, or cross-worker continuity.

See `openspec/specs/codexcont-continuation-middleware/context.md` for
rationale, upstream semantics, and operational notes.

## Requirements
### Requirement: WebSocket Responses Stream Continuation Folding
codex-lb SHALL apply CodexCont continuation folding to continuation-eligible
Responses streams served over the downstream WebSocket transport
(`/backend-api/codex/responses`), governed by the same
`CODEX_LB_CODEX_CONTINUATION_ENABLED` gate and eligibility rules as the HTTP path
(continuation enabled, streaming, reasoning not explicitly disabled). When
continuation is disabled or the request is ineligible, the WebSocket transport
MUST relay upstream events unchanged. Folding MUST be applied in-place within the
upstream relay so failover, auth retry, previous-response recovery, and
tool-call de-duplication continue to apply to eligible turns.

#### Scenario: Truncated WebSocket round continues
- **WHEN** a downstream WebSocket Responses turn is continuation eligible and its
  upstream terminal event reports `usage.output_tokens_details.reasoning_tokens`
  matching `truncation_step * n - 2` with encrypted reasoning available
- **AND** configured continuation caps allow another round
- **THEN** codex-lb does not emit the truncated round's tentative final output to
  the downstream client
- **AND** codex-lb opens a continuation round that appends the prior encrypted
  reasoning plus the configured continuation marker to the next upstream request
- **AND** the downstream client receives the folded rounds as one coherent
  response stream with continuous output indexes and sequence numbers

#### Scenario: WebSocket continuation disabled
- **WHEN** `CODEX_LB_CODEX_CONTINUATION_ENABLED=false` or the request disables
  reasoning
- **THEN** the downstream WebSocket transport relays upstream events without
  opening hidden continuation rounds

### Requirement: WebSocket Hidden Rounds Reuse Selected Upstream
Hidden WebSocket continuation rounds MUST reuse the already-selected upstream
account, authorization headers, upstream route, and Codex client/session of the
visible round. They MUST NOT re-enter account selection as separate
user-visible requests and MUST NOT create independent API-key usage
reservations.

#### Scenario: Hidden WebSocket round stays on the selected account
- **WHEN** a WebSocket continuation round is opened for a truncated turn
- **THEN** the round is sent to the same upstream account and route as the
  visible round
- **AND** no additional account selection or API-key reservation is created for
  the hidden round

### Requirement: WebSocket Settlement Uses Proxy Billed Usage
codex-lb WebSocket settlement MUST use `metadata.proxy_billed_usage` (the true
aggregated usage across folded rounds) for API-key usage settlement and
request-log usage whenever a WebSocket Responses terminal event carries it,
rather than the agent-facing `response.usage`. Downstream clients MUST still
receive the agent-facing `response.usage`. When no `metadata.proxy_billed_usage`
is present, settlement MUST use `response.usage` as before.

#### Scenario: Folded WebSocket stream settles aggregated usage
- **WHEN** a folded WebSocket stream returns agent-facing `response.usage` and
  `metadata.proxy_billed_usage`
- **THEN** downstream clients receive the agent-facing `response.usage`
- **AND** codex-lb API-key settlement and request logs record
  `metadata.proxy_billed_usage`

#### Scenario: Unfolded WebSocket stream settles response usage
- **WHEN** a WebSocket terminal event has no `metadata.proxy_billed_usage`
- **THEN** codex-lb API-key settlement and request logs record `response.usage`

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

### Requirement: Continuation Fold Decisions Emit A Prometheus Counter
codex-lb MUST increment a Prometheus counter `codex_lb_codex_continuation_decision_total`, labeled `transport`, `decision`, and `tier`, exactly once per fold round terminal whose usage matches the reasoning-token truncation fingerprint (truncation tier present), on both the HTTP pull fold and the WebSocket push fold. The `transport` label MUST be `http` or `websocket`. The `decision` label MUST be drawn from the closed set `continue`, `buffered_tool_calls`, `missing_round_anchor`, `no_encrypted_content`, `max_continue`, `max_total_output_tokens`, `tier_out_of_window`, `stop`. The `tier` label MUST be the truncation tier rendered as a bounded low-cardinality string, with tiers above a fixed cap collapsed into a single overflow bucket. Round terminals that do not match the truncation fingerprint MUST NOT increment the counter, and decision recording MUST be a no-op when the optional Prometheus dependency is unavailable.

#### Scenario: WebSocket fold continues past a truncated round
- **WHEN** a WebSocket fold round terminal matches the truncation fingerprint at tier 1
- **AND** the fold opens a hidden continuation round
- **THEN** the counter increments once with `transport=websocket`, `decision=continue`, `tier=1`

#### Scenario: Chained truncated round with a buffered tool call is counted as a stop
- **WHEN** a chained WebSocket turn's truncated round emitted a client-answered tool call and the fold stops instead of opening a hidden round
- **THEN** the counter increments once with `transport=websocket` and `decision=buffered_tool_calls`

#### Scenario: HTTP fold terminal stop is counted
- **WHEN** an HTTP pull-fold round terminal matches the truncation fingerprint
- **AND** configured caps or the tier window stop the fold
- **THEN** the counter increments once with `transport=http` and the stop reason as the `decision` label

#### Scenario: Non-truncated terminal emits no sample
- **WHEN** a fold round terminal does not match the truncation fingerprint
- **THEN** the counter is not incremented for that terminal

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

### Requirement: WebSocket Continuity State Is Persisted To A Shared Store
codex-lb MUST persist a session's WebSocket continuity state — last completed
input count, last completed response id, last completed input-prefix
fingerprint, pending function-call ids, and folded response-id aliases — to a
shared `websocket_continuity_states` store keyed by
`(session_key, api_key_id)` (empty string when no API key), after each
recorded continuity completion: both the plain `response.completed` path and
the fold-terminal path, where the persisted snapshot MUST include any
just-recorded folded response-id alias. States without a continuity key
(codex session affinity disabled, or no session id derivable from the
connection headers) MUST NOT be persisted.

#### Scenario: Plain completion persists the continuity snapshot
- **WHEN** a keyed WebSocket turn completes with `response.completed` and the
  continuity completion is recorded
- **THEN** codex-lb schedules exactly one upsert of the state snapshot to the
  shared store under the session's `(session_key, api_key_id)` key

#### Scenario: Fold terminal persists the alias with the snapshot
- **WHEN** a folded WebSocket turn completes and records a
  `visible_id -> final_round_upstream_id` alias on the continuity state
- **THEN** the persisted snapshot includes that alias in
  `folded_response_id_aliases`

#### Scenario: Unkeyed states are never persisted
- **WHEN** a WebSocket connection has codex session affinity disabled or no
  session id in its headers
- **THEN** no read from or write to the shared store occurs for that
  connection's continuity state

### Requirement: WebSocket Connections Hydrate Continuity State On Setup
codex-lb MUST, when a downstream WebSocket connection's continuity lookup
misses the worker's in-memory index, attempt to hydrate the freshly created
state from the shared store exactly once at connection setup, before the
relay loop starts. Hydration MUST apply only while the state is pristine
(all fields at defaults) so persisted data can never overwrite fresher
in-memory data, and hydrated fields MUST be defensively validated (including
re-applying the folded-alias bound) before use. A lookup that hits the
in-memory index MUST NOT read the store.

#### Scenario: Cross-worker reconnect restores the folded alias
- **WHEN** a client whose folded turn completed on worker A reconnects to
  worker B, whose in-memory index has no entry for the session
- **AND** the shared store holds the session's persisted continuity state
- **THEN** worker B hydrates the state at connection setup, including
  `folded_response_id_aliases`
- **AND** a follow-up turn sending the folded (visible) response id as
  `previous_response_id` is rewritten to the final hidden round's upstream id
  without a fail-closed retry

#### Scenario: In-memory hit skips the store
- **WHEN** the connection's continuity lookup finds an existing state in the
  worker's in-memory index
- **THEN** no store read is performed and the in-memory state is used as-is

### Requirement: Continuity-State Persistence Never Blocks The Relay
Continuity-state persistence MUST be best-effort and non-blocking: writes
MUST run as tracked background tasks that the relay never awaits, each task
MUST open its own database session scope (never sharing a session with the
relay or another task), and the persisted payload MUST be snapshotted
synchronously at schedule time so later turns cannot mutate an in-flight
write. Within a worker, writes for one state MUST be ordered such that an
older snapshot never overwrites a newer one. Task failures MUST be logged
via the task set's completion handling, not raised into the relay.

#### Scenario: The relay does not wait for the store
- **WHEN** a continuity completion schedules a persistence write
- **THEN** the downstream terminal event is delivered without awaiting the
  write

#### Scenario: A failed write does not disturb the turn
- **WHEN** the background upsert raises (for example, the database is
  unavailable)
- **THEN** a warning is logged and the downstream event text is unchanged
- **AND** the in-memory continuity state remains authoritative for the
  connection

### Requirement: Continuity Store Failures Degrade To In-Memory Behavior
Any failure of the shared continuity-state store MUST degrade to the
per-worker in-memory-only behavior that exists today and MUST NOT fail the
WebSocket relay: a missing table (mid-rollout), an unavailable database, an
absent repository binding, and a corrupt or non-conforming persisted payload
MUST each result in a warning and an empty (or unhydrated) state. Warning
log lines MUST NOT contain raw session identifiers; identifiers MUST be
hashed following the existing continuity observability convention. Stale
persisted data read by another worker MUST be recoverable through the
existing fail-closed continuity retry, never through corruption of the turn.

#### Scenario: Hydration read failure yields an empty state
- **WHEN** the store read at connection setup raises
- **THEN** a warning is logged with a hashed session identifier
- **AND** the connection proceeds with a fresh empty continuity state and the
  relay operates exactly as it does today

#### Scenario: Corrupt persisted payload is discarded
- **WHEN** the persisted row's payload fails JSON decoding or field
  validation
- **THEN** hydration is skipped and the connection proceeds with the empty
  state

#### Scenario: Absent repository skips the store entirely
- **WHEN** the repository bundle provides no continuity-state repository
  (for example, before the migration lands)
- **THEN** hydration and persistence are skipped without error

