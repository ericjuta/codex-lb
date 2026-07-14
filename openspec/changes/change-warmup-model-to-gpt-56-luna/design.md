## Context

Warmup model selection currently has three default surfaces: the env-backed application setting, the `dashboard_settings.warmup_model` ORM/database default, and the quota-planner warm-now fallback. The quota-planner fallback duplicates the old model literal, while the bootstrap model catalog already contains `gpt-5.6-luna`.

## Goals / Non-Goals

**Goals:**

- Make `gpt-5.6-luna` the shared default for otherwise-unconfigured warmup execution.
- Keep the quota-planner fallback aligned with the env-backed application setting.
- Update the declarative and database server defaults, with migration coverage for existing installations.
- Preserve explicit dashboard and quota-planner model choices.

**Non-Goals:**

- Do not change the model catalog, pricing, routing policy, or request schema.
- Do not overwrite existing persisted `dashboard_settings.warmup_model` values.
- Do not change the separate limit-warmup model setting.

## Decisions

1. **Use the application setting as the quota-planner fallback.** `QuotaWarmupService` will resolve an absent planner preference through `get_settings().warmup_model` instead of introducing another `gpt-5.6-luna` literal. This keeps environment overrides and the planner behavior on one source of truth. A second hardcoded fallback was rejected because it can drift from application configuration.

2. **Update both ORM and database defaults.** `DashboardSettings` will declare `gpt-5.6-luna` for Python and server-side defaults. A new forward-only Alembic revision will alter the existing column's server default; the historical migration remains unchanged. Updating rows in place was rejected because the database cannot distinguish an operator-selected `gpt-5.4-mini` from an old default.

3. **Validate the public settings surface.** The example environment and settings API default regression will use `gpt-5.6-luna`, while tests that intentionally exercise explicit legacy model values will remain unchanged.

## Risks / Trade-offs

- [Existing persisted settings retain the prior model] -> This avoids silently overriding operator choices; operators can update the persisted setting through the existing settings API.
- [The target model may be unavailable in an external upstream catalog] -> The repository's bootstrap catalog already includes `gpt-5.6-luna`; normal upstream model validation remains unchanged.
- [A migration adds a new Alembic revision] -> Use the current single head as the parent, provide a downgrade to the prior server default, and run migration policy/schema checks.

## Migration Plan

1. Deploy the code/config default and the forward-only server-default migration.
2. Apply the migration through the normal upgrade path and verify migration policy and schema drift checks.
3. Existing persisted settings remain unchanged; new settings rows and inserts without an explicit model receive `gpt-5.6-luna`.
4. Roll back by downgrading the new revision and restoring the prior code defaults if required.

## Open Questions

None.
