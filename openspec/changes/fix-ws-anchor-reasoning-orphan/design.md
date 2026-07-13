## Context

The websocket continuity anchor (`_websocket_continuity_anchor_for_payload`,
helpers.py:410) converts a client full replay into `previous_response_id` +
`input[stored_count:]` at mixin.py:1723-1738. Validation today covers only the
prefix fingerprint (`_input_prefix_matches_stored_context`, service.py:2456).
Nothing checks the *delta* itself. Codex clients omit `reasoning` items they
cannot replay, so `stored_count` — recorded from a completed prior turn — can
land between a `reasoning` item and its paired assistant `message` in the
*current* replay, producing a delta whose first items are assistant outputs
orphaned from their reasoning siblings. Upstream rejects this with 400
`invalid_request_error` "Item 'msg_…' … without its required 'reasoning' item:
'rs_…'", and the raw error kills the downstream turn.

Live evidence (2026-07-13): every failing `request_logs` row is preceded in the
same second by `websocket_session_anchor_injected`; 18 occurrences since
2026-07-09, concentrated in luna/sol incremental-delta sessions.

## Goals / Non-Goals

Goals
- Never emit an anchored delta that upstream will reject for reasoning pairing.
- If upstream still rejects a proxy-injected anchor this way, recover with the
  already-retained full replay instead of surfacing the raw 400.
- Keep both changes observable via distinct log reasons.

Non-Goals
- No change to client-authored `previous_response_id` handling.
- No change to prompt-cache placement, sticky routing, or the trim helper's
  handling of leading assistant prefixes ending in tool outputs.
- No attempt to synthesize missing reasoning items (upstream requires the
  original encrypted content; fabrication is impossible).

## Decisions

### D1: Guard shape — validate the delta, not the boundary
Add `_websocket_anchor_delta_is_reasoning_consistent(delta_items)` in
helpers.py and call it inside the anchor-injection site (drop the anchor when
it fails). Rule: an assistant `message` item that is not preceded by a
`reasoning` item *within the delta* marks an unsafe boundary; everything else
is consistent.

Post-deploy soak (2026-07-13) corrected the initial conservative rule, which
rejected any delta containing assistant `message`/`reasoning` items. Live
traffic showed incremental codex clients structurally lead every delta with
the prior turn's outputs (`reasoning`, tool calls, sometimes a visible
`message`), so the conservative rule skipped ~95% of anchor opportunities
(64 skips vs 3 injects in the first 9 minutes) while weeks of pre-fix logs
prove upstream accepts and dedupes re-sent reasoning/tool-call items on
anchored turns. The rejected upstream shape is specifically an assistant
`message` without a `reasoning` sibling in the same payload, so the precise
rule keys on exactly that.

Alternative rejected: precise `rs_`/`msg_` sibling matching by shared hex
stem — undocumented upstream contract, breaks silently if ID format changes.
The ordering rule ("some reasoning precedes the message in the delta") can in
principle misjudge a cross-boundary pairing; D2 recovery transparently
replays the retained full payload in that case, degrading to the conservative
behavior rather than an error.

### D2: Recovery classifier — extend the existing stale-anchor path
`mixin.py` already retains `fresh_upstream_request_text` +
`fresh_upstream_request_is_retry_safe` for proxy-injected anchors and replays
it when `_is_previous_response_not_found_error(...)` matches. Add a sibling
classifier `_is_orphaned_reasoning_item_error(code, message)` matching
`invalid_request_error` + message containing "without its required 'reasoning'
item", and let it trigger the same recovery branch only when
`request_state.proxy_injected_previous_response_id` is true. Client-authored
anchors keep today's pass-through behavior.

### D3: Observability
- Skip: log `websocket_session_anchor_skipped request_id=… reason=reasoning_orphan
  original_items=… stored_count=…` at INFO.
- Recovery: reuse the existing recovery log path with a distinct
  reason/classifier tag so the two flows are separable in logs.

## Risks / Trade-offs

- D1's conservative rule disables the anchor for any delta containing
  assistant outputs, sending full replays upstream in those cases. Cost:
  larger payload + upstream folds it (this is exactly what the client sent
  anyway, and what happens today for non-anchored models). Benefit: zero
  false-negative orphans. The luna delta-mode cached-ratio behavior is
  unaffected (notes.md, improve-prompt-cache-hit-rate: caching is an upstream
  accounting property, not anchor-dependent).
- D2 message-substring matching can drift if upstream rewords the error. The
  guard (D1) is the primary fix; D2 is defense-in-depth, and a wording drift
  degrades to today's behavior (raw error), not to something worse.
- Retry loop risk: recovery replay strips `previous_response_id`, so a second
  orphaned-reasoning 400 cannot recur on the replay; no loop bound needed
  beyond the existing single-replay guard.

## Migration Plan

Code + tests only; no schema, config, or API surface change. Deploy via
`./update.sh` as usual. Rollback = revert the commit.

## Open Questions

- Should the skip also fire when the delta contains a bare `reasoning` item
  with no message (reasoning-only tail)? Current answer: yes, same
  conservative rule — full replay is always safe.
