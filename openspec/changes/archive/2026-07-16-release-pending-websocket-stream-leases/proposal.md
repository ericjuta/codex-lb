## Why

A downstream WebSocket can submit a new `response.create` before the previous upstream reader has finished, allowing an account stream lease to be overwritten or removed with pending request state without being released. The leaked `inflight_streams` count can prematurely exhaust an otherwise healthy account's stream capacity.

## What Changes

- Release the connection's current account stream lease before adopting a lease reserved on the next pending WebSocket request.
- Release and clear any request-owned account stream lease when pending WebSocket requests are failed during disconnect or teardown.
- Add regression coverage proving orphaned pending-request leases no longer leave account stream pressure elevated.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `responses-api-compat`: Strengthen the account stream lease lifecycle requirement so replacement and pending-request cleanup release every acquired lease exactly once.

## Impact

- Affects WebSocket Responses request lifecycle cleanup in `app/modules/proxy/_service/websocket/mixin.py`.
- Adds focused proxy utility regression coverage.
- Does not change external APIs, configuration, persistence schema, or dependencies.
