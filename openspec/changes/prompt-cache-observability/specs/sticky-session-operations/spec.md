## ADDED Requirements

### Requirement: Dashboard cached-token percentage uses input-token denominator

The dashboard token statistic MUST compute the displayed cached percentage as cached input tokens divided by input tokens when an input-token total is available in the metrics payload, and MUST fall back to the combined input-plus-output total only when the input-token total is absent. The displayed cached-token count MUST remain the cached input token total.

#### Scenario: Input-token denominator is used when available

- **WHEN** the dashboard metrics payload includes an input-token total alongside the combined token total and cached input tokens
- **THEN** the cached meta label shows the cached count and the percentage of cached input tokens relative to input tokens

#### Scenario: Fallback when input totals are absent

- **WHEN** the metrics payload lacks an input-token total
- **THEN** the cached percentage falls back to the combined token total as denominator
