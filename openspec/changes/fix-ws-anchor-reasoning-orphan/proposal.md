## Why

The websocket continuity-anchor optimization (`websocket_session_anchor_injected`)
rewrites a client's self-contained full replay into `previous_response_id` +
a sliced delta (`input[stored_count:]`). When the slice boundary separates an
assistant `message` item from its paired `reasoning` item, upstream rejects the
request with HTTP 400 `invalid_request_error` ("Item 'msg_…' of type 'message'
was provided without its required 'reasoning' item: 'rs_…'"), the raw error is
forwarded downstream, and the user turn hard-fails. Live `request_logs` shows
18 such failures since 2026-07-09, 8 of them on 2026-07-13 between 16:13 and
16:31 UTC on `gpt-5.6-luna`/`gpt-5.6-sol` incremental-delta sessions, including
a visibly "hung" interactive Codex turn.

## What Changes

- Anchor-injection guard: before replacing a full replay with an anchored
  delta, validate that the sliced delta is self-consistent — it must not
  contain an assistant `message` (or other reasoning-paired output item)
  whose required `reasoning` sibling falls on the other side of the slice
  boundary. When the delta would be inconsistent, skip anchor injection and
  forward the client's original full replay unchanged.
- Recovery classifier: treat the upstream 400 "provided without its required
  'reasoning' item" invalid-request error the same way as
  `previous_response_not_found` for proxy-injected anchors — reconnect and
  replay the retained self-contained full payload (`fresh_upstream_request_text`)
  as a fresh turn instead of forwarding the raw error and ending the turn.
- Observability: log a distinct reason when anchor injection is skipped by the
  new guard and when the recovery replay fires, so live incidents are
  attributable without payload capture.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `responses-api-compat`: The existing requirement family "WebSocket
  full-resend previous-response misses retry without stale anchor" /
  "Codex WebSocket stale-anchor failures remain recoverable by a full-context
  retry" gains two requirement-level changes: (1) proxy-side anchor injection
  MUST NOT produce a delta that orphans a reasoning-paired item, and (2) the
  upstream orphaned-reasoning invalid-request error on a proxy-injected anchor
  MUST trigger the retained full-payload replay rather than surfacing the raw
  error.

## Impact

- Code: `app/modules/proxy/_service/websocket/helpers.py`
  (`_websocket_continuity_anchor_for_payload`, delta self-consistency check,
  error classifier), `app/modules/proxy/_service/websocket/mixin.py`
  (anchor-injection call site ~1723-1856, error-event recovery path
  ~3383-3521).
- Tests: regression coverage at the websocket product path — anchored-slice
  orphan is prevented (guard) and, if upstream still returns the orphan 400 on
  a proxy-injected anchor, the retained full replay fires (recovery).
- No API, schema, or migration changes. No dashboard changes beyond log lines.
- Risk: guard makes some turns send full replays (larger upstream payloads,
  slightly lower prompt-cache delta benefit) only in the rare inconsistent-
  boundary case; behavior today for those turns is a hard failure.
