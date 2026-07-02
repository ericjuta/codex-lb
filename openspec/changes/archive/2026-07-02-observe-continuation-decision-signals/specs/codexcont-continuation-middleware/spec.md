## ADDED Requirements

### Requirement: Continuation Fold Decisions Emit A Prometheus Counter
codex-lb MUST increment a Prometheus counter `codex_lb_codex_continuation_decision_total`, labeled `transport`, `decision`, and `tier`, exactly once per fold round terminal whose usage matches the reasoning-token truncation fingerprint (truncation tier present), on both the HTTP pull fold and the WebSocket push fold. The `transport` label MUST be `http` or `websocket`. The `decision` label MUST be drawn from the closed set `continue`, `buffered_tool_calls`, `missing_round_anchor`, `no_encrypted_content`, `max_continue`, `max_total_output_tokens`, `tier_out_of_window`, `stop`. The `tier` label MUST be the truncation tier rendered as a bounded low-cardinality string, with tiers above a fixed cap collapsed into a single overflow bucket. Round terminals that do not match the truncation fingerprint MUST NOT increment the counter, and decision recording MUST be a no-op when the optional Prometheus dependency is unavailable.

#### Scenario: WebSocket fold continues past a truncated round
- **WHEN** a WebSocket fold round terminal matches the truncation fingerprint at tier 1
- **AND** the fold opens a hidden continuation round
- **THEN** the counter increments once with `transport=websocket`, `decision=continue`, `tier=1`

#### Scenario: Chained truncated round with a buffered tool call is counted as a stop
- **WHEN** a chained WebSocket turn's truncated round emitted a client-answered tool call and the fold stops instead of opening a hidden round
- **THEN** the counter increments once with `transport=websocket` and `decision=buffered_tool_calls`

#### Scenario: HTTP fold terminal stop is counted
- **WHEN** an HTTP pull-fold round terminal matches the truncation fingerprint
- **AND** configured caps or the tier window stop the fold
- **THEN** the counter increments once with `transport=http` and the stop reason as the `decision` label

#### Scenario: Non-truncated terminal emits no sample
- **WHEN** a fold round terminal does not match the truncation fingerprint
- **THEN** the counter is not incremented for that terminal
