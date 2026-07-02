# Tasks

## 1. Settlement prerequisite (safe, ship first)
- [x] 1.1 Make `_finalize_websocket_request_state` prefer
  `metadata.proxy_billed_usage` over `event.response.usage` for API-key
  settlement and request-log usage, mirroring `_stream_usage_accounting`.
- [x] 1.2 Unit test coverage for billed-usage settlement (folded terminal path).

## 2. WebSocket continuation folding (native, in-place)
- [x] 2.1 No separate flag: fold is governed by the existing
  `CODEX_LB_CODEX_CONTINUATION_ENABLED` gate (same eligibility as the HTTP path).
- [x] 2.2 Port the fold state machine to a push model
  (`websocket/continuation.py` `_WebSocketContinuationFold`) reusing the exact
  HTTP fold helpers (index/sequence rewriting, buffered final answer, usage
  summation, proxy metadata).
- [x] 2.3 Drive the fold in-place inside `_process_upstream_websocket_text` for
  clean success events; on truncation resend a hidden continuation round over the
  same upstream/account via `upstream_control.continuation_resend_body` (no new
  account selection or API-key reservation); finalize the reconstructed terminal
  (settles `metadata.proxy_billed_usage`).
- [x] 2.4 Preserve failover / auth retry / previous-response recovery / tool-call
  de-dup: only clean success events fold; error and continuity-corruption
  terminals fall through to the normal relay path. Reset the fold on
  replay/failover. Transparent passthrough when disabled/ineligible.

## 3. Tests & validation
- [x] 3.1 Fold unit tests (`test_websocket_continuation_fold.py`): truncated→clean
  fold, monotonic sequence, suppressed truncated output, summed billed usage;
  non-truncated passthrough.
- [x] 3.2 WebSocket integration tests: truncated turn folds with a hidden round on
  the same upstream, final answer from the hidden round, settlement bills summed
  usage; non-truncated eligible turn completes in one round.
- [x] 3.3 `openspec validate --strict`, `ruff`, full `test_proxy_websocket_responses`
  suite (no regressions vs main; no hangs).
- [x] 3.4 Live validation on the local deployment: confirm `reasoning_tokens` no
  longer clusters on the `518*n - 2` boundary and error/latency are steady.
  (Verified 2026-07-02 during the live-verification loops that produced the
  fix-ws-fold-previous-response-chaining follow-up; fold decisions observed via
  `codex_lb_codex_continuation_decision_total`.)
