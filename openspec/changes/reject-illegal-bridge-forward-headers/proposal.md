## Why

Owner-forwarded HTTP bridge requests reconstruct WebSocket metadata as HTTP
headers before posting to the target replica. If reconstructed bridge metadata
contains illegal HTTP control characters, aiohttp can reject serialization
outside the proxy's structured error path. If reservation metadata were merely
omitted, the origin could also continue treating an owner as settlement
authority without transmitting the reservation identity.

## What Changes

- Reject illegal control characters in signed bridge-forward context metadata
  before signatures are built or an owner request is posted.
- Drop unsafe ordinary client headers rather than forwarding them to aiohttp.
- Preserve horizontal tab in header values as permitted by the existing wire
  contract, while rejecting it in header names.
- Fail closed when reservation metadata is unsafe instead of selectively
  omitting signed reservation headers.
- Preserve the fork's existing file-affinity and continuity-owner boundaries;
  this change validates only fields already present in its forward context.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `sticky-session-operations`: owner forwarding fails closed on illegal
  reconstructed HTTP header metadata.

## Impact

The change is limited to owner-forward header construction and its unit/service
coverage. It adds no forwarded identity field, selection policy, retry circuit,
or load-balancer contract.
