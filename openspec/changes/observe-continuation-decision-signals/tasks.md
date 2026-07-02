# Tasks

## 1. Fail-closed variant labels

- [x] 1.1 Add `_missing_tool_output_variant(*, code, param, message) ->
      str | None` to `app/modules/proxy/service.py` (returns
      `"missing_tool_output"` / `"orphaned_tool_output"` / `None`; same
      `invalid_request_error` + `param=input` guard, one variant per message
      prefix) and reimplement `_is_missing_tool_output_error` as
      `_missing_tool_output_variant(...) is not None`.
- [x] 1.2 Add a `_missing_tool_output_variant` stub to
      `app/modules/proxy/_service/http_bridge/service_stubs.py` (same
      `_service_global` dispatch pattern as the existing boolean stub).
- [x] 1.3 `app/modules/proxy/_service/websocket/helpers.py`:
      `_rewrite_websocket_continuity_corruption_event` gains
      `upstream_error_code: str | None = None` and forwards it to
      `_record_continuity_fail_closed`;
      `_maybe_rewrite_websocket_previous_response_not_found_event` computes
      the variant, uses it as the reason, changes the reconnect gate to
      `variant is not None or request_state.preferred_account_id is not None`,
      and passes the normalized upstream error code;
      `_sanitize_websocket_previous_response_error` uses the variant as the
      reason (upstream_error_code already passed). No change to
      `_websocket_continuity_error_fields` (both variants fall through to
      `stream_incomplete`) or to the boolean-only sites
      (`_websocket_precreated_retry_error_code`, archive matcher).
- [x] 1.4 `app/modules/proxy/_service/websocket/mixin.py`
      (`_process_upstream_websocket_text`): compute
      `missing_tool_output_variant` and the normalized upstream error code
      before `rewrite_parallel_tool_call_text` mutates the payload; derive
      `is_missing_tool_output_event` from the variant; pass
      `reason=missing_tool_output_variant` and
      `upstream_error_code=` into the corruption rewrite; replace the
      grouped-error-reason `"missing_tool_output"` literal with the variant.
- [x] 1.5 `app/modules/proxy/_service/http_bridge/upstream_events.py`: same
      variant + pre-mutation code capture; grouped-error-reason literal and
      the per-request corruption rewrite use the variant; add
      `upstream_error_code` passthrough.
- [x] 1.6 `app/modules/proxy/_service/streaming/helpers.py`
      (`_rewrite_previous_response_stream_error`): replace the boolean check
      + `reason="missing_tool_output"` with the variant helper.
- [x] 1.7 Grep `app/` for leftover `"missing_tool_output"` reason literals;
      the eight pre-change sites (upstream_events.py:519,617;
      websocket/mixin.py:3127,3144; websocket/helpers.py:878,882,1035;
      streaming/helpers.py:493) must all be variant-driven.

## 2. Continuation decision counter

- [x] 2.1 `app/core/metrics/prometheus.py`: add
      `codex_continuation_decision_total = Counter("codex_lb_codex_continuation_decision_total",
      ..., ["transport", "decision", "tier"], registry=REGISTRY)` after
      `continuity_fail_closed_total`, plus the `None` fallback in the
      unavailable branch and the `__all__` entry.
- [x] 2.2 `app/core/clients/codex_continuation.py`: add
      `_record_continuation_decision(*, transport, decision, tier)` (no-op
      unless `PROMETHEUS_AVAILABLE` and the counter is not `None`; `tier`
      label `str(tier)` capped at `"10+"` for tiers above 10); call it at the
      round-terminal decision point with `transport="http"`,
      `decision="continue" if should_continue_round else stopped_reason or
      "stop"`, gated on `truncation_tier is not None` (the debug log stays
      unconditional).
- [x] 2.3 `app/modules/proxy/_service/websocket/continuation.py`: call the
      shared recorder inside the existing `truncation_tier is not None`
      block with `transport="websocket"` and the same decision derivation
      (captures `buffered_tool_calls` / `missing_round_anchor` via
      `stopped_reason`).

## 3. Regression coverage

- [x] 3.1 Unit: `_missing_tool_output_variant` returns each exact variant
      string and `None` for near-miss code/param/message
      (extend the classifier tests in `tests/unit/test_proxy_utils.py`).
- [x] 3.2 websocket_stream surface: orphaned-variant corruption rewrite
      increments `continuity_fail_closed_total` with
      `reason="orphaned_tool_output"`, logs `upstream_error_code`, and keeps
      the external code `stream_incomplete` (locks
      `_websocket_continuity_error_fields` fallthrough).
- [x] 3.3 Relay-level regression: clone the
      `_process_upstream_websocket_text` missing-tool-output masking test
      with the orphaned message (externally failing surface).
- [x] 3.4 http_stream surface: `_rewrite_previous_response_stream_error`
      orphaned-variant clone; websocket_connect surface:
      `_sanitize_websocket_connect_failure` orphaned-variant clone.
- [x] 3.5 Bridge surface: clone the unmatched missing-tool-output masking
      test in `tests/unit/test_proxy_http_bridge.py` with the orphaned
      message (grouped reason path).
- [x] 3.6 Metric definition: extend
      `tests/unit/test_metrics.py::test_prometheus_metrics_defined_when_dependency_available`
      with the new counter name and `("transport", "decision", "tier")`
      labelnames.
- [x] 3.7 Fold emission: `tests/unit/test_websocket_continuation_fold.py`
      asserts `transport=websocket` samples for `decision=continue` (tier 1),
      `decision=buffered_tool_calls`, and zero samples for a non-truncated
      round; `tests/unit/test_codex_continuation.py` asserts
      `transport=http` samples for a continue round and a terminal stop
      (monkeypatch the `codex_continuation` module's `PROMETHEUS_AVAILABLE`
      and counter bindings, not `app.core.metrics.prometheus`).

## 4. Validation

- [x] 4.1 `.venv/bin/python -m ruff check` clean on touched files.
- [x] 4.2 Targeted pytest green: `tests/unit/test_proxy_utils.py`,
      `tests/unit/test_proxy_http_bridge.py`,
      `tests/unit/test_websocket_continuation_fold.py`,
      `tests/unit/test_codex_continuation.py`, `tests/unit/test_metrics.py`.
- [x] 4.3 `openspec validate observe-continuation-decision-signals --strict`
      passes.
