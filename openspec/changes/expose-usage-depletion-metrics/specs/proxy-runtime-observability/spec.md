## ADDED Requirements

### Requirement: Account usage depletion is observable via Prometheus

The system MUST export per-account Prometheus gauges for the latest known
usage percentage and seconds until window reset, labeled by account id and
usage window, updated whenever a usage refresh cycle persists or observes
fresh usage rows. Gauge label cardinality MUST be bounded by the number of
configured accounts and known usage windows.

#### Scenario: usage refresh updates depletion gauges

- **WHEN** the usage refresh scheduler completes a refresh cycle with a latest
  usage row for an account containing `used_percent` and `reset_at`
- **THEN** `codex_lb_account_usage_percent{account_id,window}` reports that
  `used_percent`
- **AND** `codex_lb_account_usage_reset_seconds{account_id,window}` reports the
  non-negative seconds remaining until `reset_at`

### Requirement: Transient account errors are counted by normalized code

The system MUST export a Prometheus counter of transient account errors
labeled by the normalized low-cardinality error code, incremented each time
the proxy records a transient error against an account. The label MUST NOT
contain request ids, account ids, or free-form upstream messages.

#### Scenario: websocket open timeout increments the counter

- **WHEN** an upstream websocket open timeout is recorded as a transient
  account error
- **THEN** `codex_lb_account_transient_errors_total{code="upstream_websocket_open_timeout"}`
  increments by one
