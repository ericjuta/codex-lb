# Design

## Context

Two signal-shaped follow-ups to the 2026-07-02 fold fixes:

- The shared continuity classifier now matches both tool-linkage corruption
  directions, but the reason label collapses them. The `"missing_tool_output"`
  string is **load-bearing**, not just a label: `websocket/helpers.py` gates
  `reconnect_requested` on `reason == "missing_tool_output"`, and the grouped
  terminal synthesis in `websocket/mixin.py` and
  `http_bridge/upstream_events.py` selects the grouped error reason from the
  same literal. Splitting the label must not drop reconnect/grouping behavior
  for either variant.
- Fold decisions live only in logs. The decision points already exist in both
  engines (`_stopped_reason` plus the chained-branch stops
  `buffered_tool_calls`/`missing_round_anchor`), so the counter is a pure
  emission concern.

## Decisions

### 1. Variant classification stays in the shared classifier

`_missing_tool_output_variant(*, code, param, message)` lives next to
`_is_missing_tool_output_error` in `app/modules/proxy/service.py` (same
`code == "invalid_request_error"` / `param == "input"` guard; one return value
per message-prefix branch), and `_is_missing_tool_output_error` is
reimplemented as `variant is not None`. Being a `service.py` global it is
reachable from every surface via `_facade()`; the HTTP bridge gets a matching
`service_stubs.py` entry (same `_service_global` dispatch pattern). Boolean
call sites that never surface a reason
(`_websocket_precreated_retry_error_code`, the archive matcher) keep the
boolean helper.

**Rejected:** per-surface string matching duplicated at each of the reason
sites — the exact-prefix + code + param guard would drift between surfaces.

### 2. Reuse `continuity_fail_closed_total` with a new dynamic reason value

Prometheus label values are dynamic; `orphaned_tool_output` flows into the
existing `(surface, reason)` counter with no metric definition change, and the
label-free Helm alert (`sum(rate(codex_lb_continuity_fail_closed_total[5m]))`)
keeps counting both variants. `_record_continuity_fail_closed` passes the
reason through verbatim — no observability-layer change.

**Rejected:** a separate counter for the orphaned variant — metric sprawl for
what is one operational condition with two upstream spellings.

### 3. Reconnect gate becomes "any variant matched"

`_maybe_rewrite_websocket_previous_response_not_found_event` currently
computes `reconnect_requested = reason == "missing_tool_output" or
request_state.preferred_account_id is not None`. With variant labels the gate
becomes `variant is not None or request_state.preferred_account_id is not
None`, so the orphaned variant keeps requesting the upstream reconnect that
makes the client's full-history resend succeed. Grouped-terminal reason
literals in `websocket/mixin.py` and `upstream_events.py` are replaced by the
computed variant. After the edits, no `"missing_tool_output"` literal may
remain in `app/` reason plumbing (the eight pre-change sites are enumerated in
`tasks.md`).

### 4. Capture `upstream_error_code` before payload mutation

The `websocket_stream` corruption rewrite is the only fail-closed surface that
omits `upstream_error_code` today. The normalized code must be computed in
`_process_upstream_websocket_text` (and the bridge equivalent in
`upstream_events.py`) **before** `rewrite_parallel_tool_call_text` and the
downstream response-id rewrites mutate the payload, then forwarded through a
new keyword on `_rewrite_websocket_continuity_corruption_event` into
`_record_continuity_fail_closed`. The sanitize/connect surfaces already pass
it.

### 5. Emit the decision counter from the shared fold engine

`_record_continuation_decision(*, transport, decision, tier)` lives in
`app/core/clients/codex_continuation.py` next to the round-terminal decision
logic, importing `PROMETHEUS_AVAILABLE` / `codex_continuation_decision_total`
from `app.core.metrics.prometheus` and no-oping when the optional dependency
is absent. Layering is fine: `app/core/metrics/prometheus.py` imports only
stdlib, and core→core.metrics has precedent (`app/db/sqlite_retry.py`,
`app/core/metrics/middleware.py`). The WebSocket fold
(`websocket/continuation.py`) calls the same helper inside its existing
`truncation_tier is not None` block, which naturally captures the
chained-branch stops (`buffered_tool_calls`, `missing_round_anchor`) because
they flow into `stopped_reason` before the log/emit point.

**Rejected:** parsing `metadata.proxy_continuation` off folded terminals at
the two integration call sites (`app/core/clients/proxy.py`,
`http_bridge/streaming.py`) — it re-parses data the engine already holds, only
sees final-round state (per-round decisions are lost), and risks
double-counting across the two integration points.

### 6. Gate both transports on the truncation fingerprint

The WS fold already logs only truncation-tier rounds; the HTTP fold logs every
round at debug. The counter increments only when `truncation_tier is not None`
on **both** transports, so a sample means "decision at a truncation
fingerprint" — absent samples mean no truncation, not lost data. The HTTP
debug log itself stays unconditional.

### 7. Bound the `tier` label

`tier` derives from `reasoning_tokens = 518*n - 2`; it is bounded by
`max_continue` in practice but unbounded when `codex_continuation_max_n=0`.
The recorder caps the label (tiers above 10 emit `"10+"`), keeping the label
set closed: 10 tier buckets + overflow, 8 decisions, 2 transports.

### 8. Capability mapping

The decision counter is fold-engine behavior →
`codexcont-continuation-middleware` (the capability that owns fold gates,
rounds, and terminals; introduced by `import-codexcont-middleware`). The
fail-closed variant labeling modifies the existing requirement
"Continuity-sensitive responses flows emit explicit operator diagnostics" in
`proxy-runtime-observability`, which already owns continuity fail-closed
masking diagnostics. **Rejected:** `sticky-session-operations` — it covers
sticky-session typing, rebinding, and dashboard administration, not continuity
fail-closed diagnostics.

## Risks / Trade-offs

- Splitting a load-bearing string: mitigated by keeping
  `_is_missing_tool_output_error` as a thin wrapper, replacing all eight
  reason-literal sites in one change, and pinning behavior with
  per-surface regression tests (external envelope stays `stream_incomplete`
  for both variants; `previous_response_not_found` handling untouched).
- New metric emission from a hot loop: one label lookup + increment per
  truncated round terminal only; non-truncated rounds (the common path) pay a
  single `is not None` check.
- Dashboards/alerts for the new counter are out of scope; the spec only
  guarantees the counter exists with stable label semantics.
