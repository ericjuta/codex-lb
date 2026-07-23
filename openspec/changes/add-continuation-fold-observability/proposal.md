## Why

Continuation fold decisions are currently unattributable: the
`codex_continuation_ws` log line and the
`codex_lb_codex_continuation_decision_total` counter carry no client or
reasoning-effort identity, so questions like "is folding working for
nanocodex" or "which effort level produces tier-3+ folds" require timestamp
correlation across raw logs. Additionally, `buffered_tool_calls` accounts for
~36% of live fold decisions and ceiling stops (`max_continue`) are
indistinguishable from benign terminals in terms of thinking lost, which
blocks reading the results of the planned `max_continue` A/B soak.

## What Changes

- Add low-cardinality client attribution to fold-decision observability:
  - `client` label on `codex_lb_codex_continuation_decision_total`, derived
    from the existing `useragent_group` convention
    (`_request_log_useragent_fields`), with a bounded fallback (`unknown`).
  - `effort` label on the same counter, drawn from the closed Responses
    reasoning-effort set (`none|low|medium|high|xhigh|max|unknown`) as sent in
    the request payload.
  - The same `client=... effort=...` fields on the `codex_continuation_ws`
    log line (and the HTTP-path equivalent decision log).
- Add recovered-vs-forfeited reasoning-token observability per fold decision:
  - A counter (or counter pair) recording reasoning tokens continued past a
    truncation fingerprint vs. reasoning tokens forfeited when a fold stops
    for a non-natural reason (`max_continue`, `max_total_output_tokens`,
    `no_encrypted_content`, `missing_round_anchor`), labeled by `transport`,
    `decision`, and the new `client`/`effort` labels.
  - `buffered_tool_calls` terminals are classified as natural terminals (no
    forfeit) but remain separately countable so their benignity is measurable.
- No behavior change to fold eligibility, round construction, settlement, or
  downstream event shape. Observability only.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `codexcont-continuation-middleware`: the fold-decision counter requirement
  gains `client` and `effort` labels with bounded cardinality rules, and a new
  requirement covers recovered-vs-forfeited reasoning-token recording at fold
  round terminals on both transports.

## Impact

- Runtime: `app/core/clients/codex_continuation.py`
  (`_record_continuation_decision`, HTTP fold engine),
  `app/modules/proxy/_service/websocket/continuation.py`
  (`_WebSocketContinuationFold`, decision log line),
  `app/modules/proxy/_service/websocket/mixin.py` (plumb `useragent_group` and
  request effort into the fold constructor), `app/core/metrics/prometheus.py`
  (label additions, new counter registration).
- Tests: continuation unit suites for both transports; metrics label
  assertions.
- Dashboards/queries keyed on the existing counter labels keep working
  (labels are additive); recording remains a no-op when Prometheus is
  unavailable.
- No schema, migration, API-surface, or configuration changes.
