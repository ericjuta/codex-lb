## Why

Upstream sometimes delivers the usage-limit rejection as a serialized frame (HTTP body, `response.failed`,
WebSocket `error`) with no error code. It normalized to `upstream_error`, so the fork classified it
transient: the exhausted account was never benched and the pre-created WebSocket replay refused to move.

## What Changes

- Classify a code-less (`upstream_error`) failure whose message says the usage limit is spent as `rate_limit`.
- Let the stream, compact and WebSocket health/retry decisions read the message for that one case.
- Never let a message override a code that already decided the failure (a request-shaped
  `invalid_request_error` that echoes the sentence is not benched).

## Impact

- Affected spec: `responses-api-compat`.
- Affected code: `app/core/errors.py`, `app/modules/proxy/helpers.py`, streaming/compact/WebSocket failure paths.
