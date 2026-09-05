# Sanitize WebSocket Tool-Search Fresh Replay

## Why

A direct Responses WebSocket can retain a self-contained request body for a fresh retry after a client-supplied or proxy-injected `previous_response_id` becomes stale. Replaying response-owned `id` fields from completed `tool_search_call` and `tool_search_output` items binds that otherwise fresh request to the discarded upstream response generation.

## What Changes

- Treat a WebSocket tool-search pair as fresh-retry-safe only when it is completed, ordered, self-contained, and client-owned.
- Remove only the top-level response-owned `id` from replayed `tool_search_call` and `tool_search_output` items in retained fresh-retry payloads after that check succeeds.
- Apply the sanitization to both client full-resend and proxy-injected-anchor retry payloads.
- Preserve paired tool-search content, complete input history, item order, non-tool-search fields, the ordinary anchored request path, and caller-owned input values.
- Keep HTTP resend projection, compaction, HTTP pair policy, account selection, and WebSocket ownership architecture unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `responses-api-compat`: Define response-owned tool-search ID handling for direct WebSocket full-context retries.

## Impact

- Affected code: `app/modules/proxy/_service/websocket/helpers.py` and `app/modules/proxy/_service/websocket/mixin.py`.
- Affected tests: focused public WebSocket request-preparation regressions in `tests/unit/test_proxy_utils.py`.
- Compatibility: anchored submissions keep their existing payload behavior; only the retained anchor-free retry body is sanitized.
