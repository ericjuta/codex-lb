## ADDED Requirements

### Requirement: Warmup defaults use gpt-5.6-luna

When no explicit warmup model is provided by the environment, dashboard settings, or quota-planner request, the service SHALL use `gpt-5.6-luna` for warmup model selection. The application setting, new dashboard settings rows, database server default, and quota-planner fallback SHALL agree on this value.

#### Scenario: New settings use the Terra warmup default

- **GIVEN** no `CODEX_LB_WARMUP_MODEL` override is configured
- **AND** no dashboard settings row exists
- **WHEN** application settings are loaded and dashboard settings are created
- **THEN** the persisted `warmup_model` value is `gpt-5.6-luna`
- **AND** the settings API reports `warmupModel` as `gpt-5.6-luna`

#### Scenario: Quota planner falls back to the shared Terra default

- **GIVEN** a quota-planner warm-now request has no explicit model
- **AND** `warmup_model_preference` is unset
- **WHEN** the warmup service resolves the model
- **THEN** it uses the application warmup default `gpt-5.6-luna`

#### Scenario: Explicit warmup model choices remain authoritative

- **GIVEN** an operator has an explicit dashboard or quota-planner warmup model configured
- **WHEN** a warmup is executed through that configuration
- **THEN** the configured model is used instead of the `gpt-5.6-luna` default
