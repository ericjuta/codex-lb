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
codex-lb SHALL fold downstream WebSocket Responses streams
(`/backend-api/codex/responses`) under the HTTP path's
`CODEX_LB_CODEX_CONTINUATION_ENABLED` gate and eligibility rules: continuation
enabled, streaming, and reasoning not explicitly disabled. Disabled or ineligible
turns MUST relay upstream events unchanged. Folding MUST occur in-place in the
upstream relay, preserving failover, auth retry, previous-response recovery, and
tool-call de-duplication.

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
For WebSocket Responses terminals, API-key settlement and request logs MUST use
`metadata.proxy_billed_usage` (aggregate usage across folded rounds) when present,
otherwise `response.usage`. Downstream clients MUST receive the agent-facing
`response.usage` in either case.

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
For folded WebSocket Responses turns, codex-lb MUST retain the visible round's
response id downstream and map it to the final hidden round's upstream id.
Follow-up `previous_response_id` references to the visible id MUST be forwarded
with the final round's id. Both ids MUST be registered in the previous-response
owner index for follow-up account routing.

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
Chained WebSocket hidden rounds MUST use the just-completed round's id as
`previous_response_id` and only its reasoning items plus the continuation
marker as input. They MUST NOT reuse the original anchor or replay
incremental input. Anchorless turns MUST replay full input. A truncated chained round
emitting a client-answered `function_call`, `custom_tool_call`, or `apply_patch_call`
MUST stop folding without a hidden round and deliver all buffered output,
including the call, to the client.

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
When a folded WebSocket turn completes, codex-lb MUST track as pending
(interruptible) only function calls in the folded terminal's delivered output.
On follow-up turns, interrupted-tool-output injection MUST NOT synthesize
outputs for calls absent from that output, even if a regression discarded them.

#### Scenario: Undelivered call is not treated as interrupted
- **WHEN** a folded turn's terminal output omits a `function_call` observed
  mid-turn (a discard regression) and the client answers a different
  delivered `function_call` on the next turn
- **THEN** the follow-up request forwarded upstream contains only the client's
  `function_call_output`
- **AND** no synthetic interrupted output is injected for the undelivered call

### Requirement: Orphaned Tool-Output Errors Fail Closed
On WebSocket relay and HTTP bridge paths, codex-lb MUST classify
`"No tool call found for function call output with call_id ..."`
(`type=invalid_request_error`, `param=input`) as continuity corruption,
equivalent to missing-tool-output errors. Matching turns MUST receive the
fail-closed `stream_incomplete` rewrite, not the raw upstream 400, so clients
retry with a self-contained full-history resend.

#### Scenario: Orphaned tool output on a follow-up turn is rewritten
- **WHEN** a WebSocket follow-up turn carrying `previous_response_id` receives
  the upstream error `"No tool call found for function call output with
  call_id call_X"`
- **THEN** the downstream client receives a `response.failed` terminal with
  code `stream_incomplete` and a `server_error` type
- **AND** the raw upstream message is not exposed downstream
- **AND** a `continuity_fail_closed` observation is recorded

### Requirement: Continuation Fold Decisions Emit A Prometheus Counter
For HTTP pull and WebSocket push folds, codex-lb MUST increment
`codex_lb_codex_continuation_decision_total` exactly once per round terminal
whose usage matches the reasoning-token truncation fingerprint (tier present).
Non-matching terminals MUST NOT increment the counter. Recording MUST be a no-op
when the optional Prometheus dependency is unavailable.

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

### Requirement: Continuation decision counter labels remain bounded
The continuation decision counter MUST label `transport` as `http` or
`websocket`, `decision` as one of `continue`, `buffered_tool_calls`,
`missing_round_anchor`, `no_encrypted_content`, `max_continue`,
`max_total_output_tokens`, `tier_out_of_window`, or `stop`, and `tier` as a
bounded low-cardinality truncation-tier string. Tiers above a fixed cap MUST
collapse into one overflow bucket.

#### Scenario: Counter tier exceeds its fixed cap
- **WHEN** a matching continuation terminal has a tier above the fixed cap
- **THEN** the counter uses the single overflow tier bucket

### Requirement: Truncated Rounds Emitting Client Tool Calls Stop The Fold In Every Mode
codex-lb MUST stop folding without opening another hidden round when the
just-truncated round buffered a client-answered tool call (`function_call`,
`custom_tool_call`, or `apply_patch_call`). This rule SHALL apply to chained and
anchorless WebSocket turns and the HTTP pull engine. The stopped fold MUST flush
all buffered output, including tool calls, into downstream events and the
reconstructed terminal's `output`. No fold mode SHALL discard a buffered client
tool call.

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
In every fold mode, a stop caused by a truncated round's buffered client tool
call MUST set `metadata.proxy_stopped_reason = "buffered_tool_calls"` on the
reconstructed terminal. This MUST override generic reason derivation, including
its `tier_out_of_window` fallback. The buffered-tool-call check MUST run only for
rounds that would otherwise continue. Non-fingerprint tool-call terminals MUST
remain unchanged with no stopped reason.

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
After each recorded plain `response.completed` or fold-terminal continuity
completion, codex-lb MUST persist last-completed input count, response id and
input-prefix fingerprint, pending function-call ids and folded response-id
aliases (including new aliases) in shared `websocket_continuity_states`, keyed by
`(session_key, api_key_id)` (empty string when no API key). States MUST NOT persist
without a continuity key: codex affinity disabled or no session id derivable from
connection headers.

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
On a downstream WebSocket continuity lookup miss in the worker's in-memory
index, codex-lb MUST attempt shared-store hydration of the new state exactly
once during connection setup, before the relay loop. Hydration MUST apply only
to pristine states (all fields at defaults). Fields MUST be defensively
validated before use, including re-applying the folded-alias bound. In-memory
hits MUST NOT read the store.

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
Continuity-state persistence MUST be best-effort and non-blocking. Writes MUST
run as tracked background tasks, never awaited by the relay, each with its own
unshared database session. Payloads MUST be snapshotted synchronously at schedule
time, preventing later turns from mutating in-flight writes. Within each worker,
writes for one state MUST be ordered so older snapshots cannot overwrite newer
ones. Failures MUST be logged through task-set completion handling, not raised
into the relay.

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
Shared-store failures MUST fall back to existing per-worker in-memory-only behavior,
not fail the WebSocket relay. Missing tables, unavailable databases, absent
repository bindings and corrupt/non-conforming payloads MUST yield a warning and
empty or unhydrated state. Warnings MUST hash session identifiers under the
existing continuity observability convention, never log them raw. Stale reads on
another worker MUST be recoverable by existing fail-closed continuity retry,
never corrupt the turn.

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

