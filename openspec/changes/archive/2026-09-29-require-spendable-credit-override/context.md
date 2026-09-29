# Context: require-spendable-credit-override

## Purpose and scope

A narrow fork port of upstream `da70ac5d5` (#2119). Credit metadata overrides an exhausted secondary window only when it shows spendable capacity: `credits_unlimited = true` or a positive `credits_balance`. A bare `credits_has = true` is metadata, not spendable capacity. See `specs/usage-refresh-policy/spec.md` for the normative rule.

## Decisions

- Only `_has_usable_credits` changes. Both `apply_usage_quota` consumers pick up the rule through the shared helper.
- `mappers._has_credit_override`, the rate-limited recovery trust gate, is unchanged. Upstream also leaves it unchanged.
- The upstream second requirement (`Credit-backed usage remains selectable after quota windows fill`) and #2078 status semantics are not imported.

## Constraints

- Proxy selection stays advisory (`infer_status_from_usage=False`). Usage alone never tightens an `ACTIVE` seed into `quota_exceeded`.
- For a persisted `quota_exceeded` seed, the existing runtime-reset branch still decides whether the block holds. A future reset keeps it; an elapsed or absent reset recovers it as before.
- Primary exhaustion keeps `rate_limited` precedence. `paused`, `deactivated`, and `reauth_required` pass through unchanged.

## Failure modes

- An account that omits its balance but has spendable credits is treated as exhausted until a snapshot reports `credits_unlimited = true` or a positive balance.
- After a persisted `quota_exceeded` reset deadline elapses, the proxy may recover the account through the existing advisory path even though the summary still shows `quota_exceeded`. This change narrows the gap without closing it.

## Example

Snapshot: secondary `used_percent = 100`, primary `40`, `credits_has = true`, `credits_balance = null`, `credits_unlimited = false`.

- Summary mapping (inference enabled): `quota_exceeded` with the secondary reset. It was `active` before this change.
- Proxy with a persisted `quota_exceeded` seed and a runtime reset one hour ahead: remains `quota_exceeded` and is not selected. Before this change it became `active`.
- Proxy with an `ACTIVE` seed: remains `active` (advisory, unchanged).
- The same snapshot with `credits_balance = 5` or `credits_unlimited = true`: `active` in all three cases.
