# Usage Refresh Policy Context

## Purpose

This context explains how codex-lb derives an account's usage and status, and
how to diagnose disagreements between codex-lb and Codex Desktop or the Codex
CLI quota pill.

codex-lb treats `/wham/usage` as the source of truth for account usage. Other
OpenAI account surfaces can display reset state earlier than `/wham/usage`,
especially during team reset windows, so the dashboard can temporarily show an
account as `rate_limited` even when Codex Desktop says the quota has reset.

## Upstream Usage Source

codex-lb refreshes account usage by calling:

```http
GET https://chatgpt.com/backend-api/wham/usage
```

The call is made per account on the configured refresh tick, which defaults to
60 seconds. The client lives in
[`app/core/clients/usage.py`](../../../app/core/clients/usage.py), and the
scheduler lives in
[`app/core/usage/refresh_scheduler.py`](../../../app/core/usage/refresh_scheduler.py).

## Status Derivation

The fetched usage is fed through
[`apply_usage_quota`](../../../app/core/usage/quota.py), which derives account
status from `primary_window.used_percent`:

- `secondary_used >= 100`, regardless of `primary_used`: `QUOTA_EXCEEDED`
- `used_percent >= 100` on the primary rate-limit window: `RATE_LIMITED`
- `used_percent < 100`: `ACTIVE`

There is no manual reset step inside codex-lb. Recovery is driven by the next
refresh tick that observes a sub-100 value from `/wham/usage`.

### Credit-Backed Override Requires Spendable Credits

Normative rule: "Credit-backed secondary quota remains usable" in `spec.md`.
Since the 2026-09-29 narrow port of upstream
`da70ac5d573314abc1237cdea170f599734908d1` (#2119), credit metadata overrides
an exhausted secondary window only when it shows spendable capacity:
`credits_unlimited = true` or a positive `credits_balance`. A bare
`credits_has = true` with a missing, zero, or negative balance is metadata, not
spendable capacity.

- Only the shared `_has_usable_credits` predicate changed. Summary mapping and
  proxy account-state derivation both use it through `apply_usage_quota`.
- Proxy selection stays advisory (`infer_status_from_usage=False`). Usage alone
  never tightens an `ACTIVE` seed into `quota_exceeded`. For a persisted
  `quota_exceeded` seed, the existing runtime-reset branch still decides: a
  future reset keeps the block, and an elapsed or absent reset recovers the
  account as before. This narrows the summary/proxy gap without closing it.
- Not changed: primary `rate_limited` precedence, `paused`/`deactivated`/
  `reauth_required` pass-through, cooldown handling, and
  `mappers._has_credit_override` (the rate-limited recovery trust gate, which
  upstream also leaves alone). Upstream's second credit requirement ("Credit-backed
  usage remains selectable after quota windows fill") and #2078 status semantics
  were not imported.
- Failure mode: an account with spendable credits that omits its balance is
  treated as exhausted until a snapshot reports unlimited credits or a positive
  balance.

Example: secondary `100`, primary `40`, `credits_has = true`,
`credits_balance = null`, `credits_unlimited = false`. The summary shows
`quota_exceeded` (previously `active`). A persisted `quota_exceeded` account whose
runtime reset is an hour away stays unselected. An `ACTIVE` seed stays `active`.
With `credits_balance = 5` or `credits_unlimited = true`, all three cases are
`active`.

## Why Codex Settings Can Disagree

Codex Desktop's Settings -> Account view and `/wham/usage` are fed by different
OpenAI-side data sources:

- `/wham/usage` exposes the rate limiter's internal counter. It updates lazily,
  typically on the next chargeable request through that account, or when its
  internal window crosses `reset_at`.
- Settings -> Account is fed by a separate account/quota view that often picks
  up team-side reset events earlier.

During a reset window it is normal for Settings -> Account to show the reset
state while `/wham/usage` still returns `used_percent: 100` for a short period
afterwards. codex-lb mirrors `/wham/usage` during that window, so the account
stays `RATE_LIMITED` or `QUOTA_EXCEEDED` until upstream catches up.

## Limit Warm-Up Exhaustion Threshold

Reset-confirmed limit warm-up compares the usage sample from before a refresh
with the sample written after that refresh. The pre-refresh sample must be at
or above the configured exhausted threshold, the post-refresh sample must be
below `100`, and `reset_at` must move forward.

The exhausted threshold defaults to `99.0` because some upstream usage payloads
plateau at 99 percent for windows that are practically exhausted. This avoids
missing reset-confirmed warm-ups for those accounts while keeping the reset
confirmation requirement intact. Operators who want the historical strict
behavior can set the threshold to `100.0`.

## Operational Notes

- Wait first. The next request through that account usually wakes the upstream
  rate limiter; codex-lb auto-recovers on the next refresh tick after the
  upstream payload changes.
- The dashboard Force Probe action (`POST /api/accounts/{account_id}/probe`)
  sends one fixed `responses.create` directly to the selected account,
  bypassing load-balancer scoring. It then force-refreshes that account's
  usage, invalidates the account selection cache, and returns before/after
  usage and status. The probe does not feed any replica probing-health
  recovery streak or probe-result settlement; those upstream helpers are not
  part of this fork. See "Force Probe Request Body" below.
- Do not manually flip the codex-lb account state to `ACTIVE` while
  `/wham/usage` still reports the account as fully used. That only masks the
  upstream state and can route traffic back to an account that the upstream
  limiter will reject.

## Force Probe Request Body

Normative rule: "Force Probe upstream request omits unsupported output-token
limit" in `spec.md`. Since the 2026-09-29 narrow port of upstream
`f8ffbac2099a113fba54dfd8d77774f5bca80ffa` (#2496), the probe body contains no
`max_output_tokens` key at any value. There is no replacement cap, setting,
sanitizer, or retry. Ordinary Responses forwarding already strips the field
(`_UNSUPPORTED_UPSTREAM_FIELDS` in `app/core/openai/requests.py`); the fixed
probe body was the only path that still sent it. Limit warm-up's separate
`max_output_tokens=4` goes through `ResponsesRequest` and is stripped there.

- Evidence boundary: upstream #2496 reports HTTP 400 `Unsupported parameter:
  max_output_tokens` for a body with `16` and HTTP 200 without the field. This
  fork has not reproduced that against live upstream. Local evidence is a
  loopback stub that rejects the field. It proves that the fork no longer sends
  the field and that the upstream status reaches the operator. It does not
  prove current live upstream behavior.
- Supersession history: `add-account-probe-endpoint` sent
  `max_output_tokens=1`. `probe-valid-token-floor` raised it to `16` after
  [#1895](https://github.com/Soju06/codex-lb/issues/1895) reported
  `1 → 400, 16 → 200`, and forbade lower values. Those two changes were
  archived on 2026-09-29 without spec sync. Their output-token clauses are
  superseded and must not be reintroduced into this spec. Their endpoint,
  eligibility, snapshot, and dashboard clauses were never synced either. They
  remain historical records, not canonical requirements. The canonical spec
  covers only the Force Probe request-body contract. For example, the code also
  refuses `reauth_required` accounts, which the historical `409` scenario did
  not list.
- Failure mode: if the field returns, an upstream that rejects it answers 400.
  The probe reports `probeStatusCode: 400` for a usable account and the limiter
  is not woken. Because nothing retries, the single request's status stays
  visible.

```json
{
  "model": "gpt-5.5",
  "instructions": "Respond with a single dot.",
  "input": [{"role": "user", "content": [{"type": "input_text", "text": "."}]}],
  "stream": true,
  "store": false
}
```

## Verification Example

To confirm that the disagreement is upstream rather than codex-lb's mirror,
call `/wham/usage` directly with the same account token codex-lb is using:

```bash
ACCESS_TOKEN=...
ACCOUNT_ID=...   # chatgpt-account-id UUID, not codex-lb's id

curl -s https://chatgpt.com/backend-api/wham/usage \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "chatgpt-account-id: ${ACCOUNT_ID}" \
  -H "Accept: application/json" | jq '.rate_limit'
```

If `primary_window.used_percent` is still `100` here while Settings -> Account
shows the account as reset, codex-lb has nothing fresher to mirror. The account
is inside the upstream propagation window, and the practical fix is to wait or,
once #677 lands, use the Probe action.

## Related Work

- [#676 - initial bug report on `/wham/usage` vs. Settings UI divergence](https://github.com/Soju06/codex-lb/issues/676)
- [#677 - dashboard per-account force-probe action](https://github.com/Soju06/codex-lb/issues/677)
