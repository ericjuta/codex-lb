# Responses API Compatibility Context

## Purpose and Scope

This capability implements OpenAI-compatible behavior for `POST /v1/responses`, including request validation, streaming events, non-streaming aggregation, and OpenAI-style error envelopes. The scope is limited to what the ChatGPT upstream can provide; unsupported features are explicitly rejected.

See `openspec/specs/responses-api-compat/spec.md` for normative requirements.

## Rationale and Decisions

- **Responses as canonical wire format:** Internally we treat Responses as the source of truth to avoid divergent streaming semantics.
- **Strict validation:** Required fields and mutually exclusive fields are enforced up front to match official client expectations.
- **Cursor alias compatibility:** Cursor UI model labels may append reasoning or speed suffixes to GPT-5 slugs; those are normalized to canonical upstream fields before forwarding.
- **No truncation support:** Requests that include `truncation` are rejected because upstream does not support it.
- **Compact as a separate contract:** Standalone compact is treated as a canonical opaque context-window contract, not as a variant of buffered normal `/responses`.

## Constraints

- Upstream limitations determine available modalities, tool output, and overflow handling.
- `store=true` is rejected; responses are not persisted.
- `include` values must be on the documented allowlist.
- `truncation` is rejected.
- `previous_response_id` is forwarded when `conversation` is absent, but the `conversation + previous_response_id` conflict remains rejected.
- HTTP `/v1/responses` and HTTP `/backend-api/codex/responses` now use a server-side upstream websocket session bridge by default so repeated compatible requests can keep upstream response/session continuity without forcing clients onto the public websocket route.
- Codex-affinity HTTP bridge sessions can optionally use a conservative first-request prewarm (`generate=false`), but that behavior now stays behind an explicit flag so production defaults do not pay an extra upstream request unless operators opt in.
- When operators configure a multi-instance bridge ring, deterministic owner enforcement now applies only to hard continuity keys such as `x-codex-turn-state` and explicit session headers. Prompt-cache-derived bridge keys remain stable for local reuse, but in gateway-safe mode a non-owner replica may tolerate that locality miss and create or reuse a local session instead of failing with `bridge_instance_mismatch`.
- Codex-facing websocket routes now advertise `x-codex-turn-state` during websocket accept and honor client-provided turn-state on reconnect so routing can stay sticky at turn granularity even when the public websocket reconnects.
- HTTP responses routes now also return `x-codex-turn-state` headers so clients that persist response headers can promote later HTTP requests from prompt-cache affinity to stronger Codex-session continuity.
- `/v1/responses/compact` keeps a final-JSON contract and preserves the raw upstream `/codex/responses/compact` payload shape as the canonical next context window instead of rewriting it through buffered `/codex/responses` streaming.
- Compact transport failures fail closed with respect to semantics: no surrogate `/codex/responses` fallback and no local compact-window reconstruction.
- Compact transport may use bounded same-contract retries only for safe pre-body transport failures and `401 -> refresh -> retry`.
- `/v1/responses/compact` is supported only when the upstream implements it.
- `prompt_cache_key` affinity on OpenAI-style routes is intentionally bounded by a dashboard-managed freshness window, unlike durable backend `session_id` or dashboard sticky-thread routing.
- Codex-native direct websocket `/backend-api/codex/responses` treats upstream `previous_response_id` as an ephemeral anchor. If that anchor goes stale, the proxy must mask raw `previous_response_not_found` details and emit a sanitized `codex_previous_response_stale` classifier so compatible Codex clients can soft-reset and retry without `previous_response_id`.

## Fast Mode and Service Tiers

codex-lb accepts the OpenAI/Codex `service_tier` field on Responses and Chat
Completions compatible routes. The legacy `fast` spelling is accepted as an
alias and is forwarded upstream as the canonical `priority` tier.

Fast Mode is request-level intent, not a local speed guarantee. The terminal-tier
provenance repair separates three request-log values:

- `requestedServiceTier`: the client or API key's requested tier after policy
  and alias normalization, not an independent capture of upstream egress.
- `actualServiceTier`: for streams, only a nonblank tier explicitly present in
  a successful `response.completed.response`. Successful non-streaming compact
  responses may supply actual-tier evidence directly.
- `serviceTier`: the effective billable tier. An explicit terminal tier takes
  precedence; otherwise the existing observed-event/request fallback remains
  available independently of actual-tier evidence.

A completion without a tier leaves `actualServiceTier` null even if a created
or in-progress event supplied one. Missing successful terminal evidence, failed,
incomplete, cancelled, and disconnected streams provide no actual-tier evidence.
An accounting fallback must not be copied into `actualServiceTier`.

Continuation reconstruction preserves the final upstream terminal response's
`service_tier`, including its absence. It does not inherit the initial created
tier when the final terminal omits it. Proxy-synthesized incomplete responses
cannot claim a created tier as upstream terminal evidence.

These fields describe request intent, reported response metadata, and accounting.
They do not independently prove upstream scheduling or the exact egress payload.
An explicit successful terminal `auto` remains observable but is inconclusive:
it proves neither a downgrade nor priority delivery. A reported `default` is a
metadata mismatch with requested `priority`, not independent scheduling proof.
The repair leaves requested priority and transport behavior unchanged.

For OpenCode or Codex-compatible clients, enable Fast Mode by sending a
Responses request with:

```json
{
  "service_tier": "priority"
}
```

Clients that expose Fast Mode as `fast` may keep using that spelling; codex-lb
normalizes it to `priority` before forwarding.

API keys can also force the tier for traffic that uses that key. Set the key's
enforced service tier to `priority` or `fast`; both values are stored and
returned as `priority`.

Interpret records produced by the repaired logic separately from older records.
Old request logs and mismatch counters are not backfilled, corrected, or
reinterpreted as successful terminal proof. An old `auto` value may reflect an
earlier event or continuation folding; it cannot establish what the terminal
reported. Do not assume an aggregate mixes only postrepair records.

The mismatch counter covers direct streaming and compact only, not all Responses
traffic. Native WebSocket and persistent HTTP bridge request logs receive the
actual-tier repair, but those paths remain outside the counter. A zero counter,
equal tiers, or absent actual tier does not prove priority delivery.

Synthetic examples, not runtime observations, for requests asking for `priority`:

| Created tier | Successful final response tier | Actual tier after repair | Billable tier | Interpretation |
| --- | --- | --- | --- | --- |
| `auto` | `priority` | `priority` | `priority` | Continuation preserves the final reported tier, not the created tier. |
| `default` | Missing | null | `default` | Earlier tier remains an accounting fallback only; no mismatch is counted. |
| Missing | Missing | null | `priority` | Requested-tier billing fallback is not actual-tier evidence. |
| `priority` | `auto` | `auto` | `auto` | Reported metadata differs from the request; scheduling remains unknown. |

If the second example instead fails, is incomplete, is cancelled, or disconnects,
actual tier is still null and no mismatch is counted. In a pre-repair record,
a created `auto` might have obscured a terminal `priority`; the new rules do not
retroactively establish that any old record followed this synthetic sequence.

codex-lb prices requests using the effective billable `serviceTier`. Keep this
accounting choice separate from terminal evidence and from latency analysis;
these examples do not call for changing requested priority or transport.

## Include Allowlist (Reference)

- `code_interpreter_call.outputs`
- `computer_call_output.output.image_url`
- `file_search_call.results`
- `message.input_image.image_url`
- `message.output_text.logprobs`
- `reasoning.encrypted_content`
- `web_search_call.action.sources`

## Failure Modes

- **Stream ends without terminal event:** Emit `response.failed` with `stream_incomplete`.
- **Upstream error / no accounts:** Non-streaming responses return an OpenAI error envelope with 5xx status.
- **Compact upstream transport/client failure:** Retry only inside `/codex/responses/compact` when the failure is safely retryable; otherwise return an explicit upstream error without surrogate fallback.
- **HTTP bridge session closes or expires:** The next compatible HTTP `/v1/responses` or `/backend-api/codex/responses` request recreates a fresh upstream websocket bridge session; continuity is guaranteed only within the lifetime of one active bridged session.
- **Multi-instance routing without bridge owner policy:** if operators do not configure a bridge ring or front-door affinity, continuity can still fragment across replicas. With a configured bridge ring, hard continuity keys still fail closed on the wrong replica, while gateway-safe prompt-cache requests may accept locality misses instead of failing.
- **Codex websocket reconnects:** Reconnect continuity now depends on the client replaying the accepted `x-codex-turn-state`; generated turn-state is emitted on accept for backend Codex routes and echoed back when the client already supplies one.
- **Codex websocket stale previous-response anchors:** Direct backend Codex websocket stale-anchor failures are surfaced as `response.failed` / `codex_previous_response_stale` without the raw upstream code or missing `resp_...` id; OpenAI-compatible `/v1/responses` websocket clients continue to receive generic `stream_incomplete` masking.
- **Websocket handshake forbidden/not-found:** Auto transport now fails loud on `403` / `404` instead of silently hiding the websocket regression behind HTTP fallback.
- **Invalid request payloads:** Return 4xx with `invalid_request_error`.

## Error Envelope Mapping (Reference)

- 401 → `invalid_api_key`
- 403 → `insufficient_permissions`
- 404 → `not_found`
- 429 → `rate_limit_exceeded`
- 5xx → `server_error`

## Examples

Non-streaming request/response:

```json
// request
{ "model": "gpt-5.1", "input": "hi" }
```

```json
// response
{ "id": "resp_123", "object": "response", "status": "completed", "output": [] }
```

Cursor-style model alias request:

```json
{ "model": "gpt-5.4-mini-high", "input": "hi" }
```

This forwards upstream as `model: "gpt-5.4-mini"` with `reasoning.effort: "high"`.

## Operational Notes

- Pre-release: run unit/integration tests and optional OpenAI client compatibility tests.
- Smoke tests: stream a response, validate non-stream responses, and verify error envelopes.
- Post-deploy: monitor `no_accounts`, `upstream_unavailable`, compact retry attempts, and compact failure phases, especially on direct compact requests.
- Post-deploy: monitor HTTP bridge reuse/create/evict/reconnect counts and any `previous_response_not_found` or queue-saturation errors on `/v1/responses` and `/backend-api/codex/responses`.
- Post-deploy: monitor `capacity_exhausted_active_sessions`, Codex-session bridge reuse/evict counts, websocket handshake 403/404 rates after the narrower auto-fallback policy, and backend Codex HTTP vs websocket cache-ratio gaps.
- When tracing compact incidents, confirm that request logs and upstream logs show direct `/codex/responses/compact` usage without surrogate `/codex/responses` fallback.
- Post-deploy: monitor `no_accounts`, `stream_incomplete`, and `upstream_unavailable`.
- Post-deploy: monitor `codex_previous_response_stale` on `/backend-api/codex/responses`; recurring spikes mean clients are still relying on stale upstream anchors and should perform the documented full-context retry without `previous_response_id`.
- Websocket/Codex CLI tier verification runbook: `openspec/specs/responses-api-compat/ops.md`
