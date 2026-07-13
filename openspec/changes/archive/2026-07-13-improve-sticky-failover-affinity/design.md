# Design: improve-sticky-failover-affinity

## Context

`LoadBalancer.select_account` filters `exclude_account_ids` out of the candidate pool
before `_select_with_stickiness` runs. During websocket transport failover the failed
(but healthy) account is excluded per-request, so inside `_select_with_stickiness` the
pinned account is simply *absent from `states`* and the code falls into the
`pinned is None` branch, which unconditionally deletes the sticky mapping:

```
if existing:
    pinned = next((s for s in states if s.account_id == existing), None)
    if pinned is not None:
        ...outage/budget/grace handling (mapping-preserving)...
    else:
        await sticky_repo.delete(sticky_key, kind=sticky_kind)   # <- the bug
```

The `reallocate_sticky=True` delete (inside the `pinned is not None` block) is rarely
the actual eviction path in production because failover always excludes the account
first.

## Decision

**Rule: per-request exclusion never mutates sticky state.** Only pool membership
changes, permanent account status, budget pressure, or TTL expiry may delete or
rewrite a mapping.

- Thread `excluded_account_ids` from `select_account` into `_select_with_stickiness`.
- In the `pinned is None` branch: if `existing` is in the excluded set, the account is
  still in the pool but excluded for this request only (transport failover). Choose a
  fallback with `persist_fallback = False` and keep the mapping. Otherwise (account
  deleted / outside scope) delete as before.
- This applies to both kinds:
  - `prompt_cache` (TTL): next request returns to the warm account; TTL is the natural
    expiry if the account stays bad (fix #1).
  - `codex_session` (durable): the session re-homes to its original account on the next
    request once the transient failure clears, instead of permanently migrating on the
    first blip (fix #3). Genuine outages still rebind durably via the existing
    `pinned is not None` outage path (`persist_fallback` stays True for durable kinds).

## Observability

New counter `codex_lb_sticky_selection_total{kind, outcome}` recorded once per sticky
selection inside `_select_with_stickiness`:

| outcome | meaning |
|---------|---------|
| `hit` | pinned account selected (early pinned return, grace return, or pool-exhausted pinned return) |
| `fallback` | pinned unavailable; fallback chosen; mapping preserved |
| `rebind` | fallback chosen and persisted over a previous mapping |
| `new` | no prior mapping; first placement persisted |

Cardinality: 3 kinds x 4 outcomes = 12 series. Follows the existing
`_record_account_cap_rejection` guard pattern (no-op when prometheus is absent).

## Alternatives considered

- **Time-boxed re-home window for codex_session** (persist fallback, restore original
  within N seconds): more state, more writes, and the exclusion-scoped preserve rule
  achieves the same effect with none of that.
- **Metric at the mixin/service layer**: would miss non-websocket selection paths;
  `_select_with_stickiness` is the single choke point.

## Risks

- During a *sustained* single-account failure, codex_session requests now pick a
  fallback per-request (mapping still points at the failing account) instead of
  rebinding durably. Bounded by: same-account-retry + 15s connect timeout absorb
  transients; sustained account-level failures flip account status/health tier, which
  removes it from the pool or trips the `pinned is not None` outage path where durable
  rebind still occurs.
