## 1. Guard: reasoning-consistent anchor deltas (D1)

- [x] 1.1 Add `_websocket_anchor_delta_is_reasoning_consistent(delta_items)` to
      `app/modules/proxy/_service/websocket/helpers.py`: return False when the
      delta contains any assistant `message` or `reasoning` item (conservative
      rule per design D1); True otherwise.
- [x] 1.2 Call it from `_websocket_continuity_anchor_for_payload`
      (helpers.py:410) on `input[stored_count:]`; return `None` (no anchor)
      when inconsistent.
- [x] 1.3 Emit `websocket_session_anchor_skipped … reason=reasoning_orphan`
      at INFO from the anchor call site in
      `app/modules/proxy/_service/websocket/mixin.py` (~1723), including
      request_id, original_items, stored_count.
- [x] 1.4 Unit tests (tests/unit/test_proxy_utils.py or a focused new module):
      orphaned-message delta -> no anchor; tool-output-only delta -> anchor
      kept; reasoning-only tail -> no anchor; empty/user-only delta -> anchor
      kept.

## 2. Recovery: orphaned-reasoning 400 replays retained full payload (D2)

- [x] 2.1 Add `_is_orphaned_reasoning_item_error(code, message)` classifier
      next to `_is_previous_response_not_found_error` (match
      `invalid_request_error` + "without its required 'reasoning' item").
- [x] 2.2 In the websocket error-event handling paths (mixin.py ~553-574 and
      ~3383-3521), trigger the existing fresh-replay recovery branch when the
      classifier matches AND
      `request_state.proxy_injected_previous_response_id` is true AND a
      retry-safe `fresh_upstream_request_text` is retained.
- [x] 2.3 When proxy-injected but no retry-safe body is retained, surface the
      existing retryable continuity failure instead of the raw 400.
- [x] 2.4 Keep client-authored anchors pass-through (no recovery) — assert in
      tests.
- [x] 2.5 Distinct recovery log tag so skip (1.3) and replay (2.2) are
      separable in logs.

## 3. Regression coverage at the websocket product path

- [x] 3.1 Integration test in
      tests/integration/test_proxy_websocket_responses.py: full replay whose
      anchored slice would orphan a `msg_` item -> proxy sends full input
      upstream (no `previous_response_id` injected), turn succeeds.
- [x] 3.2 Integration test: proxy-injected anchor turn receives the
      orphaned-reasoning 400 before `response.created` -> upstream reconnect +
      full-payload replay -> downstream receives recovered events, not the
      raw error.
- [x] 3.3 Integration test: client-authored `previous_response_id` +
      orphaned-reasoning 400 -> raw upstream error forwarded unchanged.

## 4. Validation and ship gates

- [x] 4.1 `uv run ruff check` and focused pytest suites pass
      (unit + integration websocket modules).
- [x] 4.2 `openspec validate fix-ws-anchor-reasoning-orphan` passes; sync
      delta into `openspec/specs/responses-api-compat/spec.md` at archive.
- [x] 4.3 Deploy via `./update.sh`; confirm in live logs that
      `websocket_session_anchor_skipped reason=reasoning_orphan` appears for
      previously-failing traffic shape and `request_logs` shows no new
      "without its required 'reasoning' item" rows over a soak window.
