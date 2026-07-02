# CodexCont Continuation Middleware Context

## Purpose and Scope

The upstream Codex (ChatGPT backend) truncates reasoning at fixed tiers: a
truncated round reports `usage.output_tokens_details.reasoning_tokens` equal to
`truncation_step * n - 2` (observed step 518). This capability folds such
rounds: the tentative final output of a truncated round is suppressed, a hidden
continuation round is opened on the same upstream account carrying the prior
encrypted reasoning plus a continuation marker, and the rounds are stitched
into one downstream response with continuous output indexes and sequence
numbers.

Two transports implement the fold:

- **HTTP pull engine** — `app/core/clients/codex_continuation.py`, which also
  hosts the shared helpers (buffer types, index/sequence rewriting, terminal
  reconstruction, stop predicates, decision recorder).
- **WebSocket push fold** — `app/modules/proxy/_service/websocket/continuation.py`
  (`_WebSocketContinuationFold`), driven in-place from the upstream relay in
  `app/modules/proxy/_service/websocket/mixin.py` so failover, auth retry,
  previous-response recovery, and tool-call de-duplication keep applying.

`openspec/specs/codexcont-continuation-middleware/spec.md` holds the normative
requirements.

## Upstream Semantics (learned from live traffic, 2026-07)

- **Anchors are single-use.** Once a response chains off a
  `previous_response_id`, the upstream invalidates that anchor
  (`codex_previous_response_stale` follows within seconds if it is reused).
  Chained hidden rounds therefore chain off the just-completed round's own
  response id, with input = that round's replayed reasoning + the marker;
  the client's original anchor and the incremental tool-output input are never
  replayed (they already live in the visible round's stored context).
- **Anchored contexts must not hold unanswered tool calls.** A truncated round
  that emitted a client-answered tool call (`function_call`,
  `custom_tool_call`, `apply_patch_call`) cannot be continued past: a chained
  hidden round is rejected outright, and an anchorless/HTTP full-history
  replay would silently discard actionable output and re-think (duplicate
  side-effect risk — see `app/modules/proxy/tool_call_dedupe.py`). All fold
  modes stop with `metadata.proxy_stopped_reason = "buffered_tool_calls"` and
  deliver the buffered calls.
- **Orphaned tool output is a continuity corruption.** The upstream 400
  `"No tool call found for function call output with call_id ..."` is
  classified alongside the inverse missing-tool-output variant
  (`_missing_tool_output_variant` in `app/modules/proxy/service.py`) and
  rewritten to the fail-closed `stream_incomplete` terminal so clients retry
  with a self-contained resend.

## Decisions

- **No separate WebSocket flag:** the fold is governed by the existing
  `CODEX_LB_CODEX_CONTINUATION_ENABLED` gate with the same eligibility rules
  as the HTTP path (streaming, reasoning not explicitly disabled).
- **Hidden rounds never re-enter selection:** they reuse the visible round's
  account, headers, route, and Codex client/session, and create no independent
  API-key reservations. Ownership invariants stay intact.
- **Downstream response-id stability is an invariant:** the visible round's id
  is what clients see and chain from. A folded turn records a
  `visible_id -> final_round_upstream_id` alias
  (`folded_response_id_aliases`, bounded, on `_WebSocketContinuityState`) so a
  follow-up `previous_response_id` is rewritten to the final hidden round's id
  before trimming/anchor/injection logic; both ids register in the
  previous-response owner index.
- **Settlement prefers `metadata.proxy_billed_usage`:** the folded terminal's
  agent-facing `response.usage` understates real spend; API-key settlement and
  request logs use the aggregated billed usage when present.
- **Pending-call tracking prunes to delivered output:** defense-in-depth — no
  fold mode discards buffered client tool calls under the unified stop rule,
  but interrupted-tool-output injection must never synthesize outputs for
  calls absent from the delivered folded terminal.
- **Continuity state is shared, best-effort:** keyed states persist to
  `websocket_continuity_states` (`(session_key, api_key_id)` PK, JSON state,
  48h prune via the sticky-session cleanup loop) so cross-worker reconnects
  hydrate folded aliases. Writes are snapshotted, ordered per state, run in
  tracked background tasks with their own session scopes, and every store
  failure (missing table, DB down, absent repo, corrupt payload) degrades to
  the in-memory-only behavior with a hashed-identifier warning.
- **Decisions are observable and low-cardinality:**
  `codex_lb_codex_continuation_decision_total{transport,decision,tier}`
  increments once per truncation-fingerprint round terminal; tiers above 10
  collapse into `"10+"`; the recorder is a no-op without the optional
  Prometheus dependency.

## Failure Modes

- Fold-ineligible or disabled requests pass through unchanged; error and
  continuity-corruption terminals fall through to the normal relay path, and
  the fold resets on replay/failover.
- A stale persisted continuity snapshot read by another worker recovers via
  the existing fail-closed continuity retry (`stream_incomplete`), never via a
  corrupted turn.
- Raw upstream continuity errors are never leaked downstream; fail-closed
  rewrites carry `stream_incomplete` and record `continuity_fail_closed`
  observations (reason = classifier variant, plus the normalized upstream
  error code).

## Example

A chained WebSocket turn (client sends `previous_response_id=resp_visible`
plus a `function_call_output`) truncates at tier 1
(`reasoning_tokens = 516`). The fold suppresses the tentative output and opens
a hidden round with `previous_response_id=resp_round1` (the just-completed
round's own id) and input = round 1's reasoning items + marker. The hidden
round completes cleanly as `resp_round2`; the client receives one
`response.completed` under the original downstream id with summed
`metadata.proxy_billed_usage`, settlement bills the summed usage, the alias
`visible_id -> resp_round2` is recorded and persisted, and the next turn's
`previous_response_id` is rewritten to `resp_round2` before going upstream.
The counter records `{transport=websocket, decision=continue, tier=1}` for
round 1. Had round 1 emitted a `function_call`, the fold would instead stop,
deliver the call, and stamp `proxy_stopped_reason=buffered_tool_calls`.

## Operational Notes

- Watch `codex_lb_codex_continuation_decision_total` to confirm folding is
  active: `decision="continue"` samples should appear while client-visible
  `reasoning_tokens` stops clustering on the `518*n - 2` boundary.
- Frequent `buffered_tool_calls` stops are expected for tool-heavy agents and
  are not errors; frequent `missing_round_anchor` or fail-closed
  `orphaned_tool_output` observations indicate chaining regressions.
- The related base import of the middleware harness is tracked by the
  `import-codexcont-middleware` change (active at the time of writing); its
  requirements merge into this spec when archived.
