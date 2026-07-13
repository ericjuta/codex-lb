# prompt-cache-concentration Specification (delta)

## ADDED Requirements

### Requirement: New prompt-cache families avoid saturated accounts
The system SHALL prefer, when placing a NEW `prompt_cache` sticky family (no existing mapping), accounts whose count of recently-active large prompt-cache
families is below the configured concentration limit
(`sticky_prompt_cache_max_active_large_families_per_account`, default 2).

A prompt-cache family counts as "recently-active large" when its mapping was
updated within the configured activity window
(`sticky_prompt_cache_activity_window_seconds`, default 300) AND its observed
request input size class is large (>= `sticky_prompt_cache_large_input_bytes`,
default 65536 request-payload input bytes at classification time).

#### Scenario: New large family lands on the least-saturated account
- **WHEN** a new prompt-cache key with a large payload requires account selection
- **AND** account A has 2 recently-active large families and account B has 0
- **AND** both accounts are otherwise eligible with comparable health
- **THEN** selection places the new family on account B

#### Scenario: Saturation preference never overrides eligibility
- **WHEN** every account at or below the concentration limit is ineligible
  (excluded, unhealthy, or over budget)
- **THEN** selection falls back to the existing eligibility-ordered choice and
  MUST NOT fail the request because of concentration alone

#### Scenario: Existing warm mappings are never moved by concentration
- **WHEN** a request resolves an EXISTING `prompt_cache` mapping
- **THEN** concentration rules do not apply and the pinned account is retained
  per the existing stickiness requirements

### Requirement: Prewarm suppressed under cache pressure
The HTTP-bridge prewarm SHALL be skipped when the target account already has at
least the configured concentration limit of recently-active large prompt-cache
families, so warm-up traffic does not evict warm contexts belonging to other
sessions on the same account.

#### Scenario: Prewarm skipped on saturated account
- **WHEN** a prewarm-eligible first turn arrives for an account whose
  recently-active large family count is at or above the concentration limit
- **THEN** the prewarm is skipped with outcome `skipped_cache_pressure`
- **AND** the actual request proceeds unchanged

#### Scenario: Prewarm still runs on idle accounts
- **WHEN** a prewarm-eligible first turn arrives for an account below the limit
- **THEN** existing prewarm behavior (canary bucketing, eligibility reasons) is
  unchanged

### Requirement: Prewarm outcomes remain observable
Prewarm suppression SHALL be visible in the existing
`http_bridge_prewarm_total` metric via a distinct outcome label so the
suppression rate can be monitored without log scraping.

#### Scenario: Suppressed prewarm increments metric
- **WHEN** a prewarm is skipped due to cache pressure
- **THEN** `http_bridge_prewarm_total{outcome="skipped_cache_pressure"}` is
  incremented
