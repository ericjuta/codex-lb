# Design

## Context

The continuation fold defeats the `518*n - 2` reasoning-token truncation by
running hidden rounds and folding them into one response. It exists in three
modes:

- **HTTP pull engine** — `fold_responses_stream_with_codex_continuation`
  (`app/core/clients/codex_continuation.py`): per-round buffer of
  non-reasoning items (`_BufferedOutput`, carrying `item_type`), continue
  decision, then either an anchorless full-history replay (buffer discarded)
  or a flush + `_reconstruct_terminal`.
- **ws anchorless** — `_WebSocketContinuationFold`
  (`app/modules/proxy/_service/websocket/continuation.py`), same state
  machine in push form, full-history replay when the turn has no
  `previous_response_id`.
- **ws chained** — same class; hidden rounds chain off the just-completed
  round's own response id (the client anchor is consumed by the visible
  round).

Upstream semantics established during the 2026-07-02 live diagnosis: an
anchor is invalidated once a response chains off it, and a truncated round
that emitted a client-answered tool call cannot be continued past on a
chained anchor — the anchored context holds an unanswered call and the
upstream rejects the round. The chained ws branch therefore already stops
with `stopped_reason="buffered_tool_calls"` and delivers the calls
(b78eba7a). Anchorless replays face no such upstream rejection — they *can*
technically continue — so unifying is a product decision, not an upstream
constraint.

## Decisions

### 1. Stop-and-deliver in the anchorless modes too

A truncated round's buffered client tool call is delivered-worthy output:
continuing discards it and re-thinks, and the model may re-emit the call with
a new `call_id`, risking duplicate side effects
(`app/modules/proxy/tool_call_dedupe.py` guards exactly this class of bug).
Rejected alternative: keep continuing anchorless/HTTP folds and lean on
dedupe. Rejected because dedupe is a mitigation, not a contract; the client
never sees the discarded call, and fold behavior would stay mode-dependent
for the same upstream turn shape, which is confusing to operate and to spec.

### 2. One shared predicate, homed in the HTTP engine module

`_CLIENT_TOOL_CALL_ITEM_TYPES` and
`_has_buffered_client_tool_calls(entries: list[_BufferedOutput]) -> bool`
live in `app/core/clients/codex_continuation.py`, next to `_BufferedOutput`
and `_find_buffer`. The ws fold already imports the engine's private helpers
(its docstring pins byte-compatibility with the HTTP fold on reusing them),
so the existing import block is extended and the ws-local frozenset deleted.
Rejected: keeping two copies (drift between transports is exactly the bug
this change fixes). Rejected: a new shared module (disproportionate; the
dependency direction ws-fold → engine already exists).

### 3. Stopped-reason override, not `_stopped_reason` routing

`_stopped_reason` returns `"tier_out_of_window"` as its fallback for any
stopped truncation-fingerprint round, so routing the new stop through it
would mislabel the reason. The engine mirrors the ws
`chained_stop_reason or _stopped_reason(...)` pattern: compute
`buffered_tool_call_stop = should_continue_round and
_has_buffered_client_tool_calls(buffered_outputs)`, force
`should_continue_round = False` when set, and pick
`"buffered_tool_calls"` directly. Evaluating the predicate only when
`should_continue_round` is already true keeps ordinary non-truncated
tool-call rounds at `stopped_reason=None` (their terminals pass through with
no `proxy_stopped_reason`). The engine's decision debug log picks up the new
reason with no change.

### 4. ws restructure: hoist the stop, keep `missing_round_anchor` chained-only

In `_on_terminal`, `chained_stop_reason` is renamed `fold_stop_reason` and
the buffered-tool-call stop moves above the
`chained_anchor is not None` guard, applying to chained and anchorless turns
alike. The `missing_round_anchor` stop (a chained round needs the completed
round's id to anchor on) stays inside the chained-only block. The rationale
comment is updated to cover both failure modes: chained rounds would anchor
an unanswered call (upstream rejects); anchorless replays would silently
discard delivered-worthy calls and re-think. The relay's fold-terminal
handling needs no change — both stop paths already flow through the same
`_FoldOutcome(downstream=..., terminal_event=...)`.

### 5. Keep the fold-terminal pending-call prune as defense-in-depth

The relay prunes `pending_function_call_ids` at fold terminal to calls
present in the delivered output (`_folded_terminal_function_call_ids`,
`app/modules/proxy/_service/websocket/helpers.py`). After unification no
fold mode discards a buffered client tool call, so the prune's "discarded
call" trigger is unreachable-by-construction — but it stays as a cheap
invariant against future regressions in any mode. The sibling change's delta
requirement is reworded to the defense-in-depth framing rather than deleted;
optionally a small unit test on the helper retains direct coverage for the
integration assertion the alias-test rework retires.

### 6. Do not fix the HTTP follow-up anchoring gap here

If a *hidden* round (round >= 2) truncates while emitting a tool call, the
HTTP terminal keeps the visible round-1 response id while the upstream
stored context lives under the hidden round's id, and the HTTP path has no
fold-alias registry (that is ws-only, dc157667) — a follow-up chaining the
visible id can still 400. This is a pre-existing HTTP-engine gap. This change
narrows it (round-1 stops now dominate, so fewer tool calls originate in
hidden rounds) but does not close it; closing it is a separate concern.

## Risks / Trade-offs

- **Load-bearing test inversion.**
  `test_backend_responses_websocket_folded_turn_aliases_previous_response_id`
  (`tests/integration/test_proxy_websocket_responses.py`) feeds an anchorless
  truncated round containing `call_dropped` and asserts the fold continues;
  the unified rule inverts that. The rework removes the round-one call so the
  alias behavior stays under test via round two's `call_folded` — the
  visible-id → hidden-round-id rewrite on the follow-up is unaffected.
- **Prune coverage loss.** The `"call_dropped" not in sent_text` assertion
  becomes unconstructible once no mode discards; the prune is kept and the
  spec reworded (Decision 5) instead of deleting either.
- **Billing/observability drift.** Earlier stops shrink `proxy_rounds` and
  `proxy_billed_usage` on affected turns; settlement already prefers
  `proxy_billed_usage`. `tests/test_middleware.py`'s fold stopped-reason
  check (`max_continue`) uses a no-tool-call scenario and is unaffected.
- **Standalone middleware copy.** `middleware/proxy.py` carries its own fold
  with the old discard behavior; it is deliberately untouched (not shipped in
  the Docker image, and `app/` must not import `middleware/`).
