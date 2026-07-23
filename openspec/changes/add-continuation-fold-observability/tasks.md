## 1. Label derivation helpers

- [x] 1.1 Add a bounded client-label sanitizer (lowercase, `[a-z0-9_-]`, max 32 chars, `unknown` fallback) reusing the `_request_log_useragent_fields` group value, colocated with the continuation metrics recorder
- [x] 1.2 Add an effort-label extractor from the visible round's request body (`reasoning.effort`), validated against the closed set `none|low|medium|high|xhigh|max` with `unknown` fallback
- [x] 1.3 Unit-test both helpers: normal values, missing header/effort, oversized/hostile user-agent strings

## 2. Metrics registration

- [x] 2.1 Add `client` and `effort` labels to `codex_lb_codex_continuation_decision_total` in `app/core/metrics/prometheus.py`
- [x] 2.2 Register `codex_lb_codex_continuation_reasoning_tokens_total{transport,outcome,client,effort}` with the same optional-Prometheus no-op guard

## 3. HTTP pull fold

- [x] 3.1 Thread `client_label`/`effort_label` into `fold_responses_stream_with_codex_continuation` and `_record_continuation_decision` in `app/core/clients/codex_continuation.py`
- [x] 3.2 Record reasoning-token outcome (`recovered`/`forfeited`/`natural`) at each truncation-fingerprint terminal using the terminal round's `usage.output_tokens_details.reasoning_tokens`
- [x] 3.3 Add `client=`/`effort=` fields to the HTTP fold decision log line
- [x] 3.4 Update the HTTP fold call site (`app/core/clients/proxy.py`) to pass the derived labels

## 4. WebSocket push fold

- [x] 4.1 Thread `client_label`/`effort_label` into `_WebSocketContinuationFold` and its decision recording in `app/modules/proxy/_service/websocket/continuation.py`
- [x] 4.2 Add `client=`/`effort=` fields to the `codex_continuation_ws` log line
- [x] 4.3 Pass the already-computed `useragent_group` and payload effort at both fold construction sites in `app/modules/proxy/_service/websocket/mixin.py`, including the failover/replay reconstruction site
- [x] 4.4 Record reasoning-token outcomes at WebSocket fold terminals mirroring the HTTP classification

## 5. Tests and validation

- [x] 5.1 Extend HTTP continuation unit suite: label values on decision counter, outcome classification (`recovered`, `forfeited` via `max_continue`, `natural` via `buffered_tool_calls`), non-truncated terminals record nothing
- [x] 5.2 Extend WebSocket continuation unit suite: same assertions plus replay-reconstruction keeps labels
- [x] 5.3 Assert log lines carry `client=`/`effort=` with `unknown` fallbacks and no raw user-agent
- [x] 5.4 Run focused suites, then `uv run ruff` and repo lint/type gates
- [x] 5.5 `openspec validate --specs` passes; rebase against current head given the concurrent cherry-pick lane before opening the PR
