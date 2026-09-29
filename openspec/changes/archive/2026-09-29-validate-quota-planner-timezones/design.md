## Context

`PUT /api/quota-planner/settings` merges optional request fields with the current `PlannerSettings`, then persists the complete row through `QuotaPlannerRepository.upsert_settings`. The timezone field is free text. `_to_planner_tz` already falls back to UTC for `ZoneInfoNotFoundError`, but malformed keys (leading/trailing slash, `..` components) raise `ValueError` from `ZoneInfo`, which escapes into `build_routing_costs` and forecast building.

## Goals / Non-Goals

**Goals:**
- Reject new invalid timezone input before any settings row, selection cache, or audit side effect changes.
- Keep omitted/blank timezone input as "retain current value".
- Keep legacy stored invalid values usable by treating them as UTC.

**Non-Goals:**
- Rewriting or migrating stored legacy values.
- Changing routing costs, cooldowns, scheduler gates, or schemas beyond the timezone input contract.
- Porting upstream `_load_balancer`, model-source, fast-mode, or egress work.

## Decisions

- Validate in `api.py` with a helper beside `_validate_working_days`, raising `DashboardBadRequestError(code="invalid_quota_planner")`. This keeps the existing HTTP 400 dashboard error envelope; a Pydantic schema validator would instead produce 422 and would not know the current setting for blank retention.
- Use `ZoneInfo(normalized)` against the installed timezone database rather than a custom allowlist or slash-stripping repair. Catch both `ZoneInfoNotFoundError` and `ValueError`.
- Blank retention returns the current stored value unchanged without revalidating it, so operators can update unrelated settings on legacy rows.
- `_to_planner_tz` catches `(ZoneInfoNotFoundError, ValueError)` and keeps its UTC fallback; all forecast and routing-cost callers inherit this.

## Risks / Trade-offs

- Clients that previously saved malformed names now receive HTTP 400 → intentional; the saved values were not usable timezones.
- Legacy invalid rows silently behave as UTC → matches the existing unknown-name fallback and keeps routing non-blocking; operators can correct the value through the validated API.
