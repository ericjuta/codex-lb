# Tasks

## 1. Shared predicate (HTTP engine module)

- [x] 1.1 Add `_CLIENT_TOOL_CALL_ITEM_TYPES = frozenset({"function_call",
      "custom_tool_call", "apply_patch_call"})` near `_TERMINAL_EVENT_TYPES`
      in `app/core/clients/codex_continuation.py`, with the generalized
      rationale comment: these are real actionable output the client must
      answer; continuing past them discards them and re-thinks (duplicate
      side-effect risk — see `app/modules/proxy/tool_call_dedupe.py`), and on
      a chained anchor the upstream rejects the round outright.
- [x] 1.2 Add `_has_buffered_client_tool_calls(entries: list[_BufferedOutput])
      -> bool` near `_find_buffer`.

## 2. HTTP pull engine stop

- [x] 2.1 After computing `should_continue_round`, compute
      `buffered_tool_call_stop = should_continue_round and
      _has_buffered_client_tool_calls(buffered_outputs)` and force
      `should_continue_round = False` when set.
- [x] 2.2 Set `stopped_reason = "buffered_tool_calls" if
      buffered_tool_call_stop else _stopped_reason(...)` — override pattern;
      do NOT route through `_stopped_reason`, whose fallback would mislabel
      the stop `"tier_out_of_window"`. No other engine changes: the existing
      flush loop and `_reconstruct_terminal` already deliver the buffered
      tool calls and stamp `metadata.proxy_stopped_reason`.

## 3. ws fold unification

- [x] 3.1 Delete the local `_CLIENT_TOOL_CALL_ITEM_TYPES` in
      `app/modules/proxy/_service/websocket/continuation.py` and import
      `_has_buffered_client_tool_calls` through the existing private-import
      block from `app.core.clients.codex_continuation`.
- [x] 3.2 In `_on_terminal`, rename `chained_stop_reason` to
      `fold_stop_reason` and hoist the buffered-tool-call stop above the
      `chained_anchor is not None` guard so it applies to chained AND
      anchorless turns; keep the `missing_round_anchor` check inside a
      chained-only block; update the rationale comment to cover both modes
      (chained: upstream rejects the anchored unanswered call; anchorless:
      replay silently discards delivered-worthy calls and re-thinks).

## 4. Tests

- [x] 4.1 `tests/unit/test_codex_continuation.py`: add a sse-wrapped
      `_function_call_events(*, output_index, item_id, call_id, name)` helper
      (mirroring `tests/unit/test_websocket_continuation_fold.py`) and
      `test_fold_responses_stream_stops_and_delivers_truncated_round_tool_calls`:
      one truncated round (encrypted reasoning + function_call +
      reasoning_tokens=516) with `max_continue=3`; assert exactly one opened
      payload (no hidden round), terminal `response.completed` whose
      `response.output` contains the function_call, a downstream
      `response.output_item.done` delivering it,
      `response.metadata["proxy_stopped_reason"] == "buffered_tool_calls"`,
      and monotonic sequence numbers.
- [x] 4.2 `tests/unit/test_websocket_continuation_fold.py`: add
      `test_ws_fold_anchorless_turn_with_buffered_tool_call_stops_and_delivers`
      (clone of the chained test without `previous_response_id`, plain
      user-message input); assert `continuation is None`, the terminal
      delivers `call_next` flushed exactly once, and
      `terminal["response"]["metadata"]["proxy_stopped_reason"] ==
      "buffered_tool_calls"`; add the same metadata assert to the existing
      chained test.
- [x] 4.3 `tests/integration/test_proxy_websocket_responses.py`: add
      `test_backend_responses_websocket_anchorless_fold_stops_when_truncated_round_emits_tool_call`,
      cloned from the chained-stop integration test but with an anchorless
      request payload (no `previous_response_id`, plain input); assert
      `len(fake_upstream.sent_text) == 1`, terminal `response.completed`, and
      `delivered_call_ids == ["call_next"]`.
- [x] 4.4 Rework
      `test_backend_responses_websocket_folded_turn_aliases_previous_response_id`:
      remove round-one's `call_dropped` `_ws_function_call_events` line and
      its comment, renumber `msg_partial` to `output_index=1`, drop the
      `assert "call_dropped" not in fake_upstream.sent_text[2]` and the stale
      discard comment — under the unified rule that fold would stop at round
      one. The alias behavior under test (visible id -> hidden round id on
      the follow-up) is unaffected since round two still emits `call_folded`.
- [x] 4.5 (Optional) add a small unit test on
      `_folded_terminal_function_call_ids`
      (`app/modules/proxy/_service/websocket/helpers.py`) to retain direct
      prune coverage for the integration assertion retired in 4.4.

## 5. OpenSpec reconciliation

- [x] 5.1 Reword the `fix-ws-fold-previous-response-chaining` delta
      requirement "Folded Turns Track Only Delivered Calls As Interruptible"
      (and its "Discarded truncated-round call is not injected" scenario) to
      the defense-in-depth framing: no fold mode discards buffered client
      tool calls under the unified rule; the prune guards regressions.
- [x] 5.2 `openspec validate unify-fold-stop-on-truncated-tool-calls
      --strict` and `openspec validate fix-ws-fold-previous-response-chaining
      --strict` pass.

## 6. Validation

- [x] 6.1 `.venv/bin/python -m ruff check` clean on
      `app/core/clients/codex_continuation.py`,
      `app/modules/proxy/_service/websocket/continuation.py`, and the three
      touched test files.
- [x] 6.2 `.venv/bin/python -m pytest tests/unit/test_codex_continuation.py
      tests/unit/test_websocket_continuation_fold.py
      tests/integration/test_proxy_websocket_responses.py -q` green.
