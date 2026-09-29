## Why

Some accounts report `credits_has = true` after their secondary (weekly) window is exhausted while reporting no spendable balance. The shared usable-credit predicate treats that bare flag as credit-backed capacity, so the account summary shows an exhausted account as `active` and a persisted `quota_exceeded` block can be cleared by metadata that cannot pay for requests.

## What Changes

- Narrow port of upstream `da70ac5d5`: usable credit-backed capacity requires `credits_unlimited = true` or a positive numeric `credits_balance`.
- `credits_has = true` with a missing, zero, or negative balance no longer overrides exhausted secondary-window usage.
- Primary-window `rate_limited` precedence, operator-disabled preservation, advisory proxy selection (`infer_status_from_usage=False`), and the existing runtime-reset/cooldown behavior are unchanged.
- Not ported: upstream `_load_balancer/` decomposition, the upstream second credit requirement, upstream #2078 status semantics, and any change to `mappers._has_credit_override`.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `usage-refresh-policy`: tighten the definition of usable credit-backed capacity in `Credit-backed secondary quota remains usable`.

## Impact

- Code: `app/core/usage/quota.py` (`_has_usable_credits`), consumed by account-summary mapping and proxy account-state derivation through `apply_usage_quota`.
- Tests: existing credit cases in `tests/unit/test_account_mappers.py`, `tests/unit/test_load_balancer.py`, and applicable `tests/integration/test_load_balancer_multi_replica.py` sections.
- No schema, migration, API, setting, dashboard layout, or dependency change.
