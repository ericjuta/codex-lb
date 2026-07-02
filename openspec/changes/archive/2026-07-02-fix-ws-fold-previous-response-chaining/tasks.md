# Tasks

## 1. Folded response-id alias

- [x] 1.1 Add `folded_response_id_aliases` (bounded dict) to
      `_WebSocketContinuityState` and `folded_upstream_response_id` to
      `_WebSocketRequestState` (`app/modules/proxy/_service/support.py`).
- [x] 1.2 Expose `created_response_id` on `_WebSocketContinuationFold`
      (`app/modules/proxy/_service/websocket/continuation.py`).
- [x] 1.3 In the fold-terminal handler
      (`app/modules/proxy/_service/websocket/mixin.py`), record the
      `visible_id -> final_round_upstream_id` alias on the continuity state
      and set `folded_upstream_response_id` on the request state.
- [x] 1.4 On turn ingress, rewrite a client `previous_response_id` matching a
      recorded alias to the final round's upstream id before trimming /
      retry-safety / anchor / injection logic; log the rewrite.
- [x] 1.5 Include `folded_upstream_response_id` in
      `_websocket_continuity_response_ids` so owner registration covers both
      ids.

## 1b. Folded pending-call pruning (found via live verification)

- [x] 1b.1 Prune `pending_function_call_ids` at fold terminal to calls present
      in the folded output (`_folded_terminal_function_call_ids` in
      `websocket/helpers.py`), so interrupted-tool-output injection cannot
      synthesize outputs for calls discarded from truncated rounds.
- [x] 1b.2 Extend the alias integration test with a discarded truncated-round
      call and assert no synthetic output is injected on the follow-up.

## 1c. Chained hidden-round anchor (found via live verification, revised)

- [x] 1c.1 First attempt kept the client anchor on hidden rounds; live traffic
      showed the upstream invalidates an anchor once the visible round chains
      off it (`codex_previous_response_stale` 1s after decision=continue).
- [x] 1c.2 Chained hidden rounds now chain off the just-completed round's own
      response id with input = that round's reasoning + marker
      (`websocket/continuation.py`); anchorless turns keep full replay.
- [x] 1c.3 Integration test: chained truncating turn folds; hidden round
      chains the visible round's id and replays neither the consumed client
      anchor nor the incremental tool output.
- [x] 1c.4 When a chained truncated round emitted a client-answered tool call,
      stop the fold and deliver it (anchored hidden round would hold an
      unanswered call); unit + integration coverage.

## 2. Orphaned-tool-output classification

- [x] 2.1 Extend `_is_missing_tool_output_error`
      (`app/modules/proxy/service.py`) to match
      `"no tool call found for function call output with call_id "` in
      addition to the existing inverse variant.

## 3. Regression coverage (websocket product path)

- [x] 3.1 Integration test: folded turn whose hidden round emits a
      `function_call`; a follow-up turn on the same connection sending the
      folded (visible) id as `previous_response_id` is forwarded upstream with
      the hidden round's id.
- [x] 3.2 Integration test: upstream 400
      `"No tool call found for function call output with call_id ..."` on a
      `previous_response_id` follow-up is rewritten downstream to the
      fail-closed `stream_incomplete` `response.failed` (raw message not
      leaked).
- [x] 3.3 Unit test: classifier matches the orphaned-tool-output variant and
      still rejects near-miss codes/params.

## 4. Validation

- [x] 4.1 `uv run ruff check` clean on touched files.
- [x] 4.2 Targeted pytest (websocket integration + classifier unit files)
      green.
- [x] 4.3 `openspec validate fix-ws-fold-previous-response-chaining --strict`
      passes.
