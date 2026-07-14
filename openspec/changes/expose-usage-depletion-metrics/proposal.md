## Why

Operators cannot alert on quota exhaustion before a weekly window resets, nor on
transient upstream error storms (e.g. websocket open-timeout bursts), because
neither account usage levels nor transient error codes are exported as
Prometheus metrics. During a live storm the only evidence is log grepping, and
projected pool exhaustion is only visible in the dashboard UI.

## What Changes

- Export per-account usage gauges (`used_percent` and seconds-until-reset per
  window) refreshed on every successful usage refresh cycle, so external
  alerting can project exhaustion-before-reset (e.g. with `predict_linear`).
- Export a counter of transient account errors labeled by normalized
  low-cardinality error code, incremented where the proxy records a transient
  account error.
- No routing, selection, or client-visible behavior changes.

## Capabilities

### Modified Capabilities

- `proxy-runtime-observability`: adds usage-depletion gauges and a transient
  account error counter to the Prometheus surface.

## Impact

- Backend: metrics registry, usage refresh scheduler, proxy transient-error
  recording helper.
- Tests: unit coverage for gauge updates on refresh and counter increments on
  transient error recording.
