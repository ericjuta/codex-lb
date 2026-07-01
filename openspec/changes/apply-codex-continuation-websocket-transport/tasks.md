# Tasks

## 1. Settlement prerequisite (safe, ship first)
- [x] 1.1 Make `_finalize_websocket_request_state` prefer
  `metadata.proxy_billed_usage` over `event.response.usage` for API-key
  settlement and request-log usage, mirroring `_stream_usage_accounting`.
- [x] 1.2 Unit test: a WebSocket terminal event carrying
  `metadata.proxy_billed_usage` settles the aggregated usage; an event without it
  settles `response.usage` (regression guard).

## 2. WebSocket continuation folding
- [ ] 2.1 Add setting `codex_continuation_websocket_enabled` (env
  `CODEX_LB_CODEX_CONTINUATION_WEBSOCKET_ENABLED`, default `false`).
- [ ] 2.2 Implement an `open_round` adapter that runs a Responses round over the
  already-selected upstream account/WebSocket and yields SSE blocks.
- [ ] 2.3 For continuation-eligible WebSocket turns, drive
  `fold_responses_stream_with_codex_continuation` with the adapter and forward
  folded SSE output to the downstream client as WebSocket frames; keep hidden
  rounds on the selected account with no new reservations.
- [ ] 2.4 Preserve pending-request bookkeeping, keepalives, and reconnect/replay
  invariants for folded turns; transparent passthrough when disabled/ineligible.

## 3. Tests & validation
- [ ] 3.1 Integration test (fake upstream WebSocket): a truncated round
  (`reasoning_tokens = 518*n - 2`, encrypted content) followed by a clean round
  folds into one coherent downstream stream; truncated final output suppressed.
- [ ] 3.2 Test hidden rounds stay on the selected account and create no new
  API-key reservations.
- [ ] 3.3 `openspec validate apply-codex-continuation-websocket-transport
  --strict`, `ruff`, targeted `pytest`.
- [ ] 3.4 Gated live validation: enable the flag, confirm live `reasoning_tokens`
  no longer clusters on the `518*n - 2` boundary; disable on regression.
