# Context: validate-quota-planner-timezones

## Purpose / scope

Fork-specific port of the timezone behavior from upstream
`a3aa8caa0a18129e28b28944b389ab4dbd314b1c` (Soju06/codex-lb #2468). Normative
behavior lives in `specs/quota-phase-planner/spec.md` in this change.

## Decisions

- Validation sits in the settings API so rejection uses the existing dashboard
  HTTP 400 envelope (`invalid_quota_planner`) and happens before
  `upsert_settings`, selection-cache invalidation, and audit logging.
- `ZoneInfo` is the validator; malformed keys raise `ValueError`, unknown names
  raise `ZoneInfoNotFoundError`, and both are handled.
- Legacy rows are not migrated. Runtime conversion treats them as UTC, the same
  fallback already used for unknown names.

## Constraints

- No routing-policy, cooldown, scheduler, schema, or migration changes.
- Upstream `_load_balancer` decomposition, model sources, fast-mode policy, and
  native egress remain excluded.

## Failure mode fixed

Before this change, `PUT /api/quota-planner/settings` with
`{"timezone": "Europe/Stockholm/"}` saved the value. In shadow mode,
`build_routing_costs` then called `ZoneInfo("Europe/Stockholm/")`, raised
`ValueError`, and broke proxy account selection.

## Example

```text
PUT /api/quota-planner/settings {"timezone": "/Europe/Stockholm", "maxWarmupsPerDay": 99}
-> 400 {"error": {"code": "invalid_quota_planner", ...}}; stored settings unchanged

PUT /api/quota-planner/settings {"timezone": "  "}
-> 200; stored timezone unchanged
```
