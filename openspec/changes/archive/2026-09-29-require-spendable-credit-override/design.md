## Context

`app/core/usage/quota.py::_has_usable_credits` is the shared usable-credit predicate behind `apply_usage_quota`. It currently returns true for `credits_unlimited = true`, for any `credits_has = true`, or for a positive `credits_balance`. Its consumers are:

- account/dashboard summary mapping (`app/modules/accounts/mappers.py::_effective_status_from_usage`), which calls `apply_usage_quota` with status inference enabled;
- proxy account-state derivation (`app/modules/proxy/load_balancer.py`), which calls `apply_usage_quota(..., infer_status_from_usage=False)` so usage snapshots stay advisory for foreground selection.

Upstream `da70ac5d5` (#2119) removed the bare `credits_has` branch after a live account reported `secondary used_percent = 100`, `has_credits = true`, `balance = null`, `unlimited = false`, stayed `active`, and failed every routed request.

## Goals / Non-Goals

**Goals:**

- Usable credit-backed capacity requires `credits_unlimited = true` or a positive numeric `credits_balance`.
- Keep one shared predicate for summary mapping and proxy account-state derivation.

**Non-Goals:**

- No `_load_balancer/` decomposition, `model_sources`, fast-mode policy, or native egress changes.
- No upstream #2078 status semantics and no new selector guard. The proxy stays advisory: an `ACTIVE` seed is not tightened into `quota_exceeded` by usage, and this change does not promise an exhausted account stays unselectable until reset.
- No change to `mappers._has_credit_override`, the rate-limited recovery trust gate. Upstream also leaves it on its existing predicate.
- No change to primary/secondary precedence, operator-disabled handling, runtime-reset/cooldown handling, usage parsing, schema, settings, or API.
- Do not import upstream's second credit requirement; this fork's canonical spec has only `Credit-backed secondary quota remains usable`.

## Decisions

- Delete only the `if credits_has is True: return True` branch. The `credits_has` keyword stays on the private helpers and on `apply_usage_quota`, so no caller signatures change. LSP references show `_has_usable_credits` is called only from `quota._has_credit_override`.
  - Alternative: drop the `credits_has` parameter from the helpers. Rejected because it widens the diff to call sites for no behavior gain and diverges from upstream.
- Modify the canonical requirement in place: change only the definition of usable credit-backed capacity, copy the three existing scenarios unchanged, and add one scenario limited to summary inference and a persisted `quota_exceeded` proxy seed whose runtime reset is still in the future.

## Risks / Trade-offs

- [Risk] An upstream account may have spendable credits without reporting a balance. -> `credits_unlimited = true` still overrides, and a later snapshot with a positive balance restores the override.
- [Trade-off] Proxy protection is partial by design. A persisted `quota_exceeded` account with a bare flag remains blocked while its runtime reset is in the future; after that deadline elapses, and for an `ACTIVE` seed, existing advisory recovery applies unchanged.
- [Trade-off] The summary can still differ from the proxy for a `rate_limited` account, because `mappers._has_credit_override` keeps accepting the bare flag for rate-limited recovery. This is an intentional non-goal.
