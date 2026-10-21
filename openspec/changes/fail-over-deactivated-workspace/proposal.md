## Why

Upstream answers a revoked workspace with the structured code `deactivated_workspace`. The fork only
recognized `account_deactivated`, so that code was neither a permanent failure (the account stayed
active and every request retried the dead workspace) nor a failover trigger (the client saw the 402).

## What Changes

- Treat the exact code `deactivated_workspace` as a permanent failure that deactivates the account.
- Add the `account_unavailable` failure class and fail over to another account on it before any
  downstream-visible output.
- Do not infer the condition from a bare HTTP 402.

## Impact

- Affected spec: `responses-api-compat`.
- Affected code: `app/core/balancer/{logic,types}.py`, `app/modules/proxy/helpers.py`, raw HTTP/SSE stream and compact failover paths.
