## Why

When a hard-affinity HTTP Responses conversation loses its reusable bridge, the proxy currently injects the durable `previous_response_id` into every verified full resend before opening a fresh upstream WebSocket. A full resend that already carries complete prior output or exactly settles the prior response's direct tool-call manifest can then become eventless on the fresh connection instead of continuing from the client-supplied context.

## What Changes

- Preserve a verified client-unanchored full resend on the durable owner when no reusable local bridge or forwardable owner exists and its context is independently complete.
- Persist a response-bound, fail-closed manifest of completed direct tool calls so a tool-loop resend is accepted only when every prior call is represented and settled exactly once.
- Keep ordinary cumulative prompts, incomplete tool loops, legacy durable rows, owner-forward recovery, and account-neutral replay on their existing anchored paths.
- Add migration, repository, replay-proof, bridge unit, and public `/v1/responses` regression coverage.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `responses-api-compat`: Define when a fresh durable HTTP bridge must preserve a safe client-unanchored full resend instead of injecting a stored response anchor.

## Impact

- Affected code: HTTP bridge reattach preparation, upstream tool-call lifecycle tracking, durable bridge persistence, and one forward Alembic migration.
- Affected data: one nullable internal manifest column; existing and malformed rows remain fail-closed to anchored behavior.
- Public API schemas and account ownership rules do not change.
- This is a fork-native port of upstream commit `b5a515f0` and does not import the upstream load-balancer decomposition from `#1437`.