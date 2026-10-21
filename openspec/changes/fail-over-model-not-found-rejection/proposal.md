## Why

Upstream `model_not_found` (entitlement can differ per subscription account) reached the account-health sink
and did not move the request, so one account's missing entitlement penalized the account and failed the
request while another account could serve it.

## What Changes

- Treat the exact code `model_not_found` as a model-scoped rejection: health-neutral (no error record, no bench).
- Before acceptance, reuse the existing single replacement-account replay (`retry-stale-account-model-rejection`)
  for raw HTTP/SSE, HTTP bridge and WebSocket, preserving the original envelope when no replacement exists.
- Compact surfaces the rejection (no replay path exists there); still health-neutral.

## Impact

- Affected spec: `responses-api-compat`.
- Affected code: `app/modules/proxy/helpers.py`, streaming helpers/retry, WebSocket helpers.
