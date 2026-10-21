## Why

"Selected model is at capacity" describes the requested model, not the account. Each capacity failure
excluded the serving account for the request, so the walk rotated through (and exhausted) the whole pool
over a condition no account can serve and ended with a terminal error even after capacity cleared.

## What Changes

- On a model-capacity rejection, still record the account health write, but do not exclude the account from
  the request's selection loop (raw HTTP/SSE stream, post-refresh stream and compact paths).
- Usage-limit and quota/rate-limit classifications keep excluding (they bench the account).

Extends `retry-model-capacity-errors`, which made capacity retryable.

## Impact

- Affected spec: `responses-api-compat`.
- Affected code: `app/modules/proxy/helpers.py`, streaming retry and compact failover paths.
