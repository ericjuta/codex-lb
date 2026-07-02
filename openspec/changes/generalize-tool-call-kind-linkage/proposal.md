# Generalize Tool-Call Kind Handling In Fold Stops And Linkage Classification

## Why

Live traffic (2026-07-02 15:38 UTC) surfaced a truncated round emitting a
`tool_search_call` — a client-answered call kind outside the enumerated
`_CLIENT_TOOL_CALL_ITEM_TYPES` set (`function_call`, `custom_tool_call`,
`apply_patch_call`). Two independent guards missed it:

1. The fold's stop-and-deliver rule did not recognize the buffered item as a
   client tool call, so the chained hidden round anchored on a response with
   an unanswered call and the upstream rejected it:
   `"No tool output found for tool search call call_..."`.
2. The tool-output linkage classifier matched only the `"function call"`
   wording, so the raw 400 was relayed to the client instead of the
   fail-closed `stream_incomplete` rewrite — a hard tool error surfaced in
   the client session.

Enumerating call kinds is inherently fragile: the upstream can introduce new
client-answered call item types at any time.

## What Changes

- The buffered client-tool-call predicate (shared by the WebSocket fold and
  the HTTP pull engine) additionally treats ANY buffered output item carrying
  a non-empty `call_id` as a client-answered tool call. Client-answered call
  items carry `call_id` by construction (the output pairs on it); reasoning,
  messages, and server-executed calls (e.g. `web_search_call`) do not.
- The tool-output linkage classifier matches the invariant message frames —
  `"No tool output found for <kind> call call_..."` and
  `"No <kind> call found for <kind> output with call_id ..."` — for any call
  kind, still gated on `type=invalid_request_error` and `param=input`.

## Impact

- Folds stop and deliver on truncated rounds containing any current or future
  client-answered call kind; no hidden round can be opened past an unanswered
  call.
- Any linkage-corruption 400, regardless of call-kind wording, fails closed
  as retryable `stream_incomplete` instead of reaching the client raw.
- No schema, configuration, or metric changes.
