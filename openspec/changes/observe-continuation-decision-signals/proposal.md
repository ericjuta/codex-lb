# Observe Continuation Decision Signals

## Why

The 2026-07-02 continuation-fold fixes (`dc157667..b78eba7a`) left two
observability gaps that made the incident diagnosable only by grepping
container logs:

1. **Fail-closed variants are indistinguishable.** The continuity classifier
   (`_is_missing_tool_output_error`, `app/modules/proxy/service.py`) now
   matches two distinct upstream tool-linkage corruptions — a call whose
   output never arrived (`"No tool output found for function call call_..."`)
   and an output whose call is absent from the resolved context (`"No tool
   call found for function call output with call_id ..."`, the folded-turn
   signature) — but every surface records both as reason
   `missing_tool_output` in `codex_lb_continuity_fail_closed_total` and the
   `continuity_fail_closed` log. Operators cannot tell whether fail-closed
   volume comes from interrupted tool turns or from fold-chaining regressions.
   The `websocket_stream` surface additionally omits `upstream_error_code`
   from the structured log, unlike the connect/sanitize surfaces.
2. **Fold decisions are log-only.** The fold engines decide per truncated
   round whether to continue or stop (`continue`, `buffered_tool_calls`,
   `missing_round_anchor`, `no_encrypted_content`, `max_continue`,
   `max_total_output_tokens`, `tier_out_of_window`, `stop`) but emit only
   debug/info logs (`codex_continuation_round` in
   `app/core/clients/codex_continuation.py`, `codex_continuation_ws` in
   `app/modules/proxy/_service/websocket/continuation.py`). There is no
   Prometheus counter, so decision-mix shifts (e.g. a spike in
   `buffered_tool_calls` after an upstream behavior change) are invisible to
   dashboards and alerting.

## What Changes

- **Fail-closed variant labels.** Replace the boolean classifier's call sites
  with a variant helper `_missing_tool_output_variant(...) -> "missing_tool_output" | "orphaned_tool_output" | None`
  (same `invalid_request_error`/`param=input` guard, one variant per upstream
  message prefix). Thread the variant through every surface that today
  hardcodes the `"missing_tool_output"` reason literal: the WebSocket relay
  (`websocket/mixin.py` corruption rewrite and grouped-terminal reason), the
  WebSocket helpers (`_maybe_rewrite_websocket_previous_response_not_found_event`,
  `_sanitize_websocket_previous_response_error`), the HTTP bridge
  (`http_bridge/upstream_events.py`), and the HTTP stream fallback
  (`streaming/helpers.py`). Reconnect, grouping, and rewrite behavior stay
  identical for both variants (the reconnect gate moves from a string
  comparison to "any variant matched"). The `websocket_stream` surface starts
  passing the normalized `upstream_error_code` — captured before payload
  mutation — into `_record_continuity_fail_closed`.
- **Continuation decision counter.** Add
  `codex_lb_codex_continuation_decision_total{transport, decision, tier}`
  (`app/core/metrics/prometheus.py`) and a shared no-op-safe recorder in
  `app/core/clients/codex_continuation.py`. Both fold engines increment it
  exactly once per round terminal that matches the truncation fingerprint
  (truncation tier present): the HTTP pull fold with `transport="http"` and
  the WebSocket push fold with `transport="websocket"`. The `decision` label
  is the closed set above; the `tier` label is the truncation tier as a
  bounded string (tiers above a fixed cap collapse into one overflow bucket).
  Non-truncated round terminals do not increment the counter.
- **No external contract change.** The client-visible envelope for both
  fail-closed variants remains `stream_incomplete` (`server_error`,
  502-equivalent); `previous_response_not_found` handling is untouched.

## Impact

- Affected specs: `proxy-runtime-observability` (MODIFIED: continuity
  fail-closed diagnostics requirement), `codexcont-continuation-middleware`
  (ADDED: fold decision counter requirement).
- Affected code: `app/modules/proxy/service.py`,
  `app/modules/proxy/_service/http_bridge/service_stubs.py`,
  `app/modules/proxy/_service/websocket/helpers.py`,
  `app/modules/proxy/_service/websocket/mixin.py`,
  `app/modules/proxy/_service/http_bridge/upstream_events.py`,
  `app/modules/proxy/_service/streaming/helpers.py`,
  `app/core/metrics/prometheus.py`,
  `app/core/clients/codex_continuation.py`,
  `app/modules/proxy/_service/websocket/continuation.py`, plus unit tests.
- Metrics: one new counter (`codex_lb_codex_continuation_decision_total`).
  `codex_lb_continuity_fail_closed_total` keeps its `(surface, reason)`
  labelnames; `orphaned_tool_output` is a new dynamic `reason` value, so no
  metric definition change. The Helm alert sums the fail-closed counter
  without label filters and is unaffected.
- No schema, API-surface, persistence, or configuration changes.
