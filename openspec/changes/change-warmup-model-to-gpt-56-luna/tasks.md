## 1. Update warmup defaults

- [x] 1.1 Change the application `warmup_model` default and `.env.example` value to `gpt-5.6-luna`.
- [x] 1.2 Change the `DashboardSettings` Python and server-side defaults to `gpt-5.6-luna`.
- [x] 1.3 Replace the quota-planner warm-now hardcoded fallback with the shared application warmup setting.

## 2. Update database schema

- [x] 2.1 Add a forward-only Alembic revision from the current single head to change the `dashboard_settings.warmup_model` server default to `gpt-5.6-luna`, with a downgrade to `gpt-5.4-mini`.
- [x] 2.2 Verify the migration graph remains single-headed and the default change does not rewrite existing persisted settings.

## 3. Validate behavior and contracts

- [x] 3.1 Update settings API/default regression coverage and add focused coverage for the quota-planner fallback.
- [x] 3.2 Run focused tests for settings, warmup, and migration behavior.
- [x] 3.3 Run `openspec validate --specs`, migration policy/schema checks, and inspect the final diff/status.
