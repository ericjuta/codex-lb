## ADDED Requirements

### Requirement: OpenAI-compatible model metadata prefers the upstream max output budget

When serving `GET /v1/models`, the system MUST report a model's `max_output_tokens` (in `metadata`, `capabilities`, `max_output_tokens`, and `maxOutputTokens`) from the upstream catalog's `max_output_tokens` when that value is a positive integer. A value that is absent, zero, negative, boolean, or non-integer MUST be ignored, and the system MUST then use the known per-model output budget when one exists. That value MUST NOT be used to inflate `metadata.context_window`.

#### Scenario: Upstream max output budget overrides the slug table

- **WHEN** the upstream catalog contains `gpt-6-sol` with `max_output_tokens=96000`
- **THEN** `GET /v1/models` returns that entry with `max_output_tokens=96000` in every reported location

#### Scenario: Invalid upstream value falls back to the known budget

- **WHEN** the upstream catalog contains `gpt-6-sol` with `max_output_tokens=0`
- **THEN** `GET /v1/models` returns that entry with `max_output_tokens=128000`
