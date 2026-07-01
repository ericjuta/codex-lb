## Why

CodexCont continuation folding (defeating the `518*n - 2` reasoning-token
truncation fingerprint) was integrated into codex-lb only on the **HTTP
Responses** stream path and the HTTP session bridge (see
`import-codexcont-middleware`). The primary live transport — the **downstream
WebSocket** endpoint `/backend-api/codex/responses` that the Codex CLI uses —
opens its own upstream WebSocket relay (`_relay_upstream_websocket_messages`)
and never reaches `_stream_responses_with_session`, so continuation folding
never runs for real traffic.

Production evidence (request_logs, 45-minute live window, `bedrock_openai` /
`gpt-5.5`): of 66 `normal` client responses, **10 terminated exactly on the
`518*n - 2` boundary** (`516`, `1034`) — the exact truncation fingerprint
continuation exists to defeat — all served over `upstream_transport=websocket`,
with zero `bypassing http bridge for codex continuation` log lines. The feature
is effectively inert for live users.

Additionally, WebSocket usage settlement (`_finalize_websocket_request_state`)
bills from `event.response.usage` and never inspects
`metadata.proxy_billed_usage`. If folding is added to the WebSocket path without
fixing this, hidden continuation rounds would be **undercounted** in API-key
usage and request logs.

## What Changes

- Apply CodexCont continuation folding to the downstream-WebSocket Responses
  transport for continuation-eligible streams, gated by a new setting
  `CODEX_LB_CODEX_CONTINUATION_WEBSOCKET_ENABLED` (default off until validated
  on live traffic).
- Reuse the already-selected upstream account, auth headers, route, and Codex
  client for hidden WebSocket continuation rounds. Hidden rounds MUST NOT
  re-enter account selection or create independent API-key reservations.
- Fix WebSocket settlement so API-key usage and request logs prefer
  `metadata.proxy_billed_usage` over the agent-facing `response.usage`, mirroring
  the HTTP path's `_stream_usage_accounting`. (Shipped first as a safe
  prerequisite; it is a no-op until a folded event carries the metadata.)
- Preserve transparent passthrough for non-eligible or disabled streams: no
  behavior change when continuation is off, reasoning is explicitly disabled, or
  the request is outside the configured gates.

## Impact

- Extends the default-on continuation capability to the WebSocket transport
  (behind an explicit enable flag) so live Codex CLI traffic stops truncating at
  the `518*n - 2` fingerprint.
- Continuation-eligible WebSocket turns buffer tentative final output until
  terminal usage is known and re-chunk the final answer, matching the existing
  HTTP fold's streaming semantics (final answer is delivered at round end rather
  than token-streamed live).
- Hidden continuation rounds may increase upstream token usage on the selected
  account; reconstructed terminal metadata reports folded rounds and billed
  usage, and settlement bills the true aggregated usage.
- The settlement change is safe to deploy independently: until a WebSocket event
  carries `metadata.proxy_billed_usage`, it changes nothing.
