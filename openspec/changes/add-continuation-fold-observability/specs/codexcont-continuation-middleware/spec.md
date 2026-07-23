## MODIFIED Requirements

### Requirement: Continuation Fold Decisions Emit A Prometheus Counter
codex-lb MUST increment a Prometheus counter `codex_lb_codex_continuation_decision_total`, labeled `transport`, `decision`, `tier`, `client`, and `effort`, exactly once per fold round terminal whose usage matches the reasoning-token truncation fingerprint (truncation tier present), on both the HTTP pull fold and the WebSocket push fold. The `transport` label MUST be `http` or `websocket`. The `decision` label MUST be drawn from the closed set `continue`, `buffered_tool_calls`, `missing_round_anchor`, `no_encrypted_content`, `max_continue`, `max_total_output_tokens`, `tier_out_of_window`, `stop`. The `tier` label MUST be the truncation tier rendered as a bounded low-cardinality string, with tiers above a fixed cap collapsed into a single overflow bucket. The `client` label MUST be the request's user-agent group derived by the existing request-log convention (first user-agent token before `/`), sanitized to a bounded character set and length, with `unknown` when absent or unparseable; raw user-agent strings MUST NOT be used as label values. The `effort` label MUST be the request payload's reasoning effort drawn from the closed set `none`, `low`, `medium`, `high`, `xhigh`, `max`, with `unknown` for absent or unrecognized values. Round terminals that do not match the truncation fingerprint MUST NOT increment the counter, and decision recording MUST be a no-op when the optional Prometheus dependency is unavailable.

#### Scenario: WebSocket fold continues past a truncated round
- **WHEN** a WebSocket fold round terminal matches the truncation fingerprint at tier 1
- **AND** the fold opens a hidden continuation round
- **THEN** the counter increments once with `transport=websocket`, `decision=continue`, `tier=1`, the request's derived `client` group, and the request's `effort`

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

#### Scenario: Missing client identity falls back to a bounded label
- **WHEN** a fold round terminal matches the truncation fingerprint and no user-agent header was captured for the request
- **THEN** the counter increments with `client=unknown`

#### Scenario: Unrecognized reasoning effort falls back to a bounded label
- **WHEN** a fold round terminal matches the truncation fingerprint and the request payload carries no reasoning effort or an effort outside the closed set
- **THEN** the counter increments with `effort=unknown`

## ADDED Requirements

### Requirement: Fold Decisions Record Recovered And Forfeited Reasoning Tokens
codex-lb MUST record reasoning-token outcomes at each fold round terminal that matches the truncation fingerprint, on both the HTTP pull fold and the WebSocket push fold, via a Prometheus counter `codex_lb_codex_continuation_reasoning_tokens_total` labeled `transport`, `outcome`, `client`, and `effort`. The `outcome` label MUST be `recovered` when the fold opens a hidden continuation round (the round's reasoning tokens are carried forward), `forfeited` when the fold stops for a cap or capability reason (`max_continue`, `max_total_output_tokens`, `no_encrypted_content`, `missing_round_anchor`, `tier_out_of_window`), and `natural` when the fold stops at a natural terminal (`buffered_tool_calls`, `stop`). The recorded value MUST be the terminal round's `usage.output_tokens_details.reasoning_tokens`. The `client` and `effort` labels MUST follow the same derivation and fallback rules as the fold-decision counter. Recording MUST be a no-op when the optional Prometheus dependency is unavailable and MUST NOT alter fold behavior, round construction, settlement, or downstream events.

#### Scenario: Continued round counts recovered tokens
- **WHEN** a fold round terminal matches the truncation fingerprint with 1034 reasoning tokens
- **AND** the fold opens a hidden continuation round
- **THEN** `codex_lb_codex_continuation_reasoning_tokens_total` increases by 1034 with `outcome=recovered`

#### Scenario: Cap-stopped round counts forfeited tokens
- **WHEN** a fold round terminal matches the truncation fingerprint
- **AND** the fold stops because `max_continue` is exhausted
- **THEN** the counter increases by the terminal round's reasoning tokens with `outcome=forfeited`

#### Scenario: Buffered tool-call terminal counts as natural
- **WHEN** a fold round terminal matches the truncation fingerprint
- **AND** the fold stops because the round emitted a client-answered tool call
- **THEN** the counter increases by the terminal round's reasoning tokens with `outcome=natural`
- **AND** no `forfeited` sample is recorded for that terminal

#### Scenario: Non-truncated terminal records nothing
- **WHEN** a fold round terminal does not match the truncation fingerprint
- **THEN** no reasoning-token outcome sample is recorded for that terminal

### Requirement: Fold Decision Logs Carry Client And Effort Fields
The continuation fold decision log lines on both transports (the WebSocket `codex_continuation_ws` line and the HTTP fold decision log) MUST include `client=<useragent-group>` and `effort=<reasoning-effort>` fields using the same derivation and fallback rules as the fold-decision counter labels. Log lines MUST NOT include raw user-agent strings or raw session identifiers in these fields.

#### Scenario: WebSocket decision log carries attribution
- **WHEN** a WebSocket fold round terminal matches the truncation fingerprint for a request whose user-agent group is `nanocodex` at effort `high`
- **THEN** the emitted `codex_continuation_ws` log line includes `client=nanocodex` and `effort=high`

#### Scenario: Missing identity falls back in logs
- **WHEN** a fold decision log line is emitted for a request with no captured user-agent
- **THEN** the log line includes `client=unknown`
