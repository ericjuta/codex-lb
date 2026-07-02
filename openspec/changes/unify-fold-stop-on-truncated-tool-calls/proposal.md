# Unify Fold Stop On Truncated Tool Calls

## Why

`fix-ws-fold-previous-response-chaining` (commit b78eba7a) taught the
WebSocket continuation fold to stop and deliver when a **chained** turn's
truncated round emitted a client-answered tool call (`function_call`,
`custom_tool_call`, or `apply_patch_call`) — an anchored hidden round would
hold an unanswered call and the upstream rejects it. But the stop lives inside
the chained-only guard, so the other two fold modes still continue past such
rounds via anchorless full-history replay, silently **discarding** the
buffered tool calls:

- **ws anchorless turns** (`app/modules/proxy/_service/websocket/
  continuation.py` — the tool-call check sits under
  `if should_continue_round and chained_anchor is not None:`), and
- **the HTTP pull engine** (`app/core/clients/codex_continuation.py` — no
  tool-call stop at all).

That discard is wrong regardless of anchor mode: the buffered call is real
actionable output the client must answer. Continuing throws it away and
re-thinks the same task, risking a duplicate tool call with a fresh `call_id`
(the side-effect duplication `app/modules/proxy/tool_call_dedupe.py` exists to
guard against), and the same upstream turn shape yields different fold
behavior depending on transport and anchor presence. The observable
`metadata.proxy_stopped_reason` is likewise inconsistent: only the chained ws
branch ever reports `buffered_tool_calls`.

## What Changes

- **Shared predicate.** Hoist `_CLIENT_TOOL_CALL_ITEM_TYPES` and a new
  `_has_buffered_client_tool_calls(entries)` helper into the HTTP engine
  module (`app/core/clients/codex_continuation.py`); the ws fold deletes its
  local frozenset and imports the shared helper through its existing
  private-import block.
- **HTTP pull engine stop.** After computing `should_continue_round`, a round
  that would continue but holds a buffered client tool call is forced to stop.
  `stopped_reason` is set to `"buffered_tool_calls"` via the override pattern
  — not routed through `_stopped_reason`, whose fallback would mislabel it
  `"tier_out_of_window"`. The existing buffered-output flush and
  `_reconstruct_terminal` already deliver the calls and stamp
  `metadata.proxy_stopped_reason`.
- **ws fold unification.** Hoist the tool-call stop out of the chained-only
  guard so anchorless turns stop too (`chained_stop_reason` becomes
  `fold_stop_reason`); the `missing_round_anchor` stop remains chained-only.
- **Tests.** New HTTP-engine unit test (stop + delivery + stopped reason +
  monotonic sequence numbers); new ws unit test for the anchorless turn; new
  ws integration test on the anchorless product path; and a rework of
  `test_backend_responses_websocket_folded_turn_aliases_previous_response_id`,
  which currently encodes the old discard behavior (its anchorless round one
  buffers `call_dropped` and expects the fold to continue — inverted by the
  unified rule).
- **OpenSpec reconciliation.** Reword the sibling change's delta requirement
  "Folded Turns Track Only Delivered Calls As Interruptible": buffered tool
  calls are no longer discarded by any mode, so the fold-terminal pending-call
  prune becomes a defense-in-depth invariant rather than the discard's
  correctness backstop.

## Impact

- **Affected specs:** `codexcont-continuation-middleware` (ADDED
  requirements; the capability currently exists only as deltas in the active
  `fix-ws-fold-previous-response-chaining` change, not yet in
  `openspec/specs/`).
- **Affected code:** `app/core/clients/codex_continuation.py`,
  `app/modules/proxy/_service/websocket/continuation.py`, plus
  `tests/unit/test_codex_continuation.py`,
  `tests/unit/test_websocket_continuation_fold.py`,
  `tests/integration/test_proxy_websocket_responses.py`.
- **Behavior:** anchorless ws and HTTP folds stop one-plus rounds earlier when
  a truncated round emits a client tool call, so `proxy_rounds` /
  `proxy_billed_usage` shrink for those turns (settlement already prefers
  `proxy_billed_usage`), and `metadata.proxy_stopped_reason =
  "buffered_tool_calls"` appears on paths that never reported it. No app code
  branches on specific stopped-reason values.
- **Unchanged:** the relay's fold-terminal handling — both stop paths already
  flow through the same `_FoldOutcome(downstream=..., terminal_event=...)`,
  and the pending-call prune (`_folded_terminal_function_call_ids`) stays
  as-is. No schema, API-surface, or configuration changes.
- **Out of scope:** `middleware/proxy.py`'s standalone fold copy (not shipped
  in the Docker image; `app/` must not import `middleware/`), and the
  pre-existing HTTP follow-up anchoring gap for hidden-round stops (see
  `design.md`).
