## Why

Free-text quota planner settings currently accept malformed timezone keys such as `/Europe/Stockholm` and `Europe/Stockholm/`. Resolving these saved values during shadow-mode routing raises `ValueError` rather than using the existing UTC fallback, interrupting proxy account selection.

## What Changes

- Port only the timezone behavior from upstream `a3aa8caa0a18129e28b28944b389ab4dbd314b1c`.
- Trim supplied timezone text and validate nonblank names with `ZoneInfo` before settings persistence; reject invalid names and malformed keys with HTTP 400 and `invalid_quota_planner`.
- Preserve the current timezone when input is omitted, null, empty, or whitespace-only, including on legacy rows.
- Extend the existing UTC fallback to malformed legacy stored keys without rewriting stored settings.
- Adapt upstream API and routing-cost regressions to the fork, including trailing-slash keys and persisted-setting checks.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `quota-phase-planner`: timezone update validation and backward-compatible UTC conversion for legacy invalid settings.

## Impact

Changes are limited to `app/modules/quota_planner/api.py`, `app/modules/quota_planner/logic.py`, the existing integration/unit planner tests, and this OpenSpec change. No migration, dependency, routing-policy, cooldown, scheduler, synthetic-traffic, or frontend changes are included. Invalid updates that previously persisted will now be rejected; existing legacy rows remain readable.
