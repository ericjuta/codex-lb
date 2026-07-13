# sticky-session-operations Specification (delta)

## ADDED Requirements

### Requirement: Per-model prompt-cache efficiency is observable
The system SHALL export Prometheus counters for input tokens and cached input
tokens labeled by model and request kind
(`codex_lb_prompt_cache_input_tokens_total{model,request_kind}` and
`codex_lb_prompt_cache_cached_tokens_total{model,request_kind}`) so per-model
cache hit ratio can be derived as `cached / input` without querying the
database.

#### Scenario: Successful response updates cache-efficiency counters
- **WHEN** a proxied response completes with usage accounting
- **THEN** the input-token counter for that model and request kind increases by
  the reported input tokens
- **AND** the cached-token counter increases by the reported cached input tokens

#### Scenario: Requests without usage do not distort counters
- **WHEN** a proxied response completes without usage data
- **THEN** neither counter changes for that request
