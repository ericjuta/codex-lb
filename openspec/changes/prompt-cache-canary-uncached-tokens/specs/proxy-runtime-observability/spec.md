## ADDED Requirements

### Requirement: Prompt-cache canary tracks uncached input tokens with per-model thresholds

The prompt-cache canary MUST export, per model and sampling window, both the cache hit ratio and the average uncached input tokens per request (`(sum(input_tokens) - sum(cached_input_tokens)) / request_count`) as low-cardinality metrics. Ratio-collapse alerting MUST support per-model threshold overrides that take precedence over the blanket ratio threshold. Uncached-token alerting MUST be configurable per model (or via a blanket threshold) and MUST be disabled by default. Canary alert evaluation MUST keep the existing window, volume-floor, leader-election, and successful-normal-request filter semantics.

#### Scenario: Delta-transport rollout shrinks request inputs

- **WHEN** a model's traffic shifts from full-history replays to incremental deltas
- **AND** the per-request average input tokens drops while average uncached input tokens per request does not increase
- **AND** no uncached-token threshold is configured for the model
- **THEN** the canary exports the reduced ratio and the uncached-tokens gauge
- **AND** it does not emit an uncached-token alert for the model

#### Scenario: Per-model ratio override quiets a short-job lane

- **WHEN** a model has a configured per-model ratio threshold below the blanket threshold
- **AND** the model's sampled ratio sits between the per-model threshold and the blanket threshold with sufficient window volume
- **THEN** the canary does not emit a ratio-collapse warning for that model
- **AND** other models continue to alert against the blanket threshold

#### Scenario: Uncached-token regression alerts despite healthy ratio

- **WHEN** a model has a configured uncached-token threshold
- **AND** its average uncached input tokens per request exceeds that threshold with sufficient window volume
- **THEN** the canary emits a warning identifying the model, the average uncached tokens per request, the threshold, and the window
- **AND** the warning does not include raw prompt text, cache keys, or request payload content

#### Scenario: Defaults preserve existing behavior

- **WHEN** no per-model ratio overrides and no uncached-token thresholds are configured
- **THEN** ratio alerting behaves exactly as before against the blanket threshold
- **AND** the uncached-tokens gauge is still exported for observability
