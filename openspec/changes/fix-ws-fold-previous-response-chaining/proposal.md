# Fix WebSocket Continuation Fold `previous_response_id` Chaining

## Why

The native WebSocket continuation fold (shipped in
`apply-codex-continuation-websocket-transport`) breaks the **next turn's**
`previous_response_id` chaining whenever a folded turn ends in a tool call.

The fold's reconstructed terminal (`_reconstruct_terminal`) presents the
**visible round's** response id (R1, captured from round 1's
`response.created`) to the downstream client, but hidden continuation rounds
are sent upstream with `drop_previous_response_id=True`, so any
`function_call` emitted in round ≥ 2 lives in a **different stored upstream
response** (R2) that the client never learns about.

Live failure sequence (observed 2026-07-02 on the deployed proxy):

1. A turn truncates on the `518*n - 2` fingerprint; the fold runs a hidden
   round; the model emits `function_call call_X` in R2; the client receives a
   folded stream whose terminal carries R1.
2. The client's next turn sends `previous_response_id=R1` plus
   `function_call_output(call_X)`. Upstream resolves R1 (reasoning-only) and
   returns HTTP 400:
   `"No tool call found for function call output with call_id call_X"`
   (`type=invalid_request_error`, `param=input`).
3. codex-lb's continuity classifiers only match the **inverse** message
   (`"No tool output found for function call call_..."`), so the raw 400 is
   relayed to the client with no fail-closed rewrite and no retry — the turn
   hard-fails and the client loops on the same broken anchor.

Folded turns that end in a plain assistant message do not 400 but silently
lose round-2+ output from the upstream chain context.

## What Changes

- **Folded response-id alias (per-worker fast path).** When a folded turn
  completes, record `visible_round_id -> final_round_upstream_id` on the
  session's WebSocket continuity state. On the next turn's ingress, rewrite a
  client-supplied `previous_response_id` that matches a recorded alias to the
  final round's upstream id before trimming, retry-safety evaluation, and
  upstream forwarding.
- **Owner registration for both ids.** At fold finalize, register the final
  round's upstream response id in the previous-response owner index in
  addition to the client-visible id, so a follow-up referencing either id
  routes to the owning account.
- **Orphaned-tool-output continuity classification (cross-worker catch-all).**
  Extend the missing-tool-output continuity classifier to also match the
  upstream error `"No tool call found for function call output with
  call_id ..."`. Matching turns fail closed with the existing
  `stream_incomplete` continuity-corruption rewrite (502/response.failed +
  reconnect) instead of relaying the raw 400, so the Codex client retries with
  a self-contained full-history resend that succeeds on any worker or account.

The downstream-visible response id is intentionally **not** changed to the
final round's id: the relay preserves downstream response-id stability across
replays (`_rewrite_websocket_downstream_response_id`), and clients demultiplex
concurrent turns by response id, so a `response.completed` id differing from
the turn's `response.created` id risks client-side orphaning. See `design.md`.

## Impact

- Folded WebSocket turns ending in tool calls chain correctly on the next turn
  when it lands on the same worker (transparent alias rewrite), and recover
  via one fail-closed retry otherwise — replacing today's unrecoverable 400.
- The extended classifier also applies to the HTTP bridge path (shared
  classifier), giving both transports the same fail-closed behavior for
  orphaned tool-output errors.
- No schema, API-surface, or configuration changes. No new persistence; the
  alias lives in the existing per-worker continuity LRU.
