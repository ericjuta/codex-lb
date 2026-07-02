# Design

## Context

The WebSocket continuation fold runs hidden rounds with
`drop_previous_response_id=True` (`build_round_payload`), so each hidden round
is a fresh stored upstream response. The reconstructed terminal
(`_reconstruct_terminal`) copies `base_response` — round 1's
`response.created` payload — so the client-visible id is the visible round's
id (R1) while the tool call the client must answer lives in the final round's
response (R2).

Constraints discovered during diagnosis:

- The deployment runs **8 uvicorn workers**; the continuity state
  (`_websocket_continuity_index`) and previous-response owner index
  (`_websocket_previous_response_account_index`) are **per-worker in-memory
  LRUs**. Any purely in-memory mapping misses when the client reconnects to a
  different worker.
- The relay treats **downstream response-id stability as an invariant**:
  replays pin `replay_downstream_response_id` and rewrite upstream ids back to
  the first id the client saw (`_rewrite_websocket_downstream_response_id`),
  and concurrent turns multiplexed on one socket are matched by response id.

## Decisions

### 1. Do not change the folded terminal's downstream id

Rewriting the folded `response.completed` to carry R2 would be stateless and
worker-independent, but it emits a terminal whose id differs from the turn's
`response.created` (R1, already sent before the fold decision is knowable).
A client that demultiplexes by response id would orphan the turn. This
contradicts the relay's existing id-stability invariant, so it is rejected.

### 2. Alias map on the continuity state (fast path)

`_WebSocketContinuityState` gains `folded_response_id_aliases: dict[str, str]`
(bounded FIFO, 8 entries). The fold-terminal handler records
`R1 -> R2` when they differ. Turn ingress consults the map immediately after
payload normalization — before input trimming, retry-safe evaluation, anchor
injection, and interrupted-tool-output injection — so every downstream
consumer sees the corrected id. Because
`_record_websocket_continuity_completion` already stores R2 as
`last_completed_response_id`, the rewritten id also re-enables the
interrupted-tool-output injection and full-resend retry-safety checks for
folded turns.

### 3. Register both ids in the owner index

`_WebSocketRequestState` gains `folded_upstream_response_id`; the fold
terminal handler sets it to R2 and `_websocket_continuity_response_ids`
includes it, so `_remember_websocket_previous_response_owner` maps **both**
R1 and R2 to the owning account for follow-up routing.

### 4. Fail-closed classification is the cross-worker recovery

`_is_missing_tool_output_error` additionally matches
`"no tool call found for function call output with call_id "`. Both message
variants describe the same operational condition — the turn's tool-call
linkage with the stored upstream context is corrupted — and both are handled
by the existing continuity-corruption rewrite: `stream_incomplete`
(`server_error`, 502-equivalent) plus an upstream reconnect request. The Codex
client responds to `stream_incomplete` by resending the turn with
self-contained full history, which succeeds regardless of worker or account.
This bounds the worst case (alias miss on another worker) at one extra
round-trip instead of an unrecoverable 400 loop.

Wiring is automatic: the WebSocket relay (event classification, terminal-state
popping, grouped previous-response handling, connect-failure sanitization) and
the HTTP bridge (`upstream_events.py`) all consume the shared classifier.

## Risks / Trade-offs

- The alias is per-worker; with 8 workers a reconnecting client hits the fast
  path probabilistically and the fail-closed path otherwise. Persisting the
  alias (DB) was rejected as disproportionate: it adds a write per folded turn
  to shave one retry off a minority path.
- Extending the classifier widens the set of upstream 400s converted to
  retryable `stream_incomplete` errors. The message match is prefix-anchored
  on the exact upstream wording and additionally requires
  `type=invalid_request_error` and `param=input`, matching the established
  pattern for the inverse variant.
