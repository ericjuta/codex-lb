## Why

The context-window guard added in `guard-context-window-and-build-identity` rejects any estimable request at >=90% of the model window with 400 `context_length_exceeded`. Codex clients recover from that exact error by sending a remote-compaction request — a `/backend-api/codex/responses` turn carrying a terminal `compaction_trigger` item. The guard currently runs before compaction-trigger detection, so the recovery request is itself rejected and the client deadlocks: guard 400 -> compact attempt -> guard 400 -> retries exhausted -> "ran out of room in the model's context window" (observed live 2026-07-13 12:36 UTC, five consecutive `context_window_guard_rejected` rejections).

## What Changes

- Exempt compaction-lane requests from the context-window guard: a Responses payload whose final top-level input item is a `compaction_trigger` bypasses `enforce_context_window` on every guarded path (HTTP stream, HTTP collect, websocket response.create).
- Malformed trigger placement (duplicate or non-terminal) keeps its existing fail-closed 400 validation; the exemption applies only to well-formed terminal triggers.
- Non-compaction requests keep the existing guard behavior unchanged.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `responses-api-compat`: the "Estimable context overflow is rejected before upstream connection" requirement gains a compaction-lane exemption so remote-compaction recovery requests are never guard-rejected.

## Impact

- `app/modules/proxy/request_policy.py` (guard exemption)
- Regression tests at the `/backend-api/codex/responses` route path and the websocket prepare path
- OpenSpec delta for `responses-api-compat`
