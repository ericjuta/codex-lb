# Design

## Context

The continuation fold engine `fold_responses_stream_with_codex_continuation`
(`app/core/clients/codex_continuation.py`) is transport-agnostic in shape: it
takes `open_round(payload) -> AsyncIterator[str]` yielding SSE event blocks and
returns a single folded SSE stream. It already:

- buffers non-reasoning output and flushes/rechunks the final answer only once a
  non-truncated terminal round is reached,
- discards a truncated round's tentative final output,
- rewrites downstream sequence/output indexes across rounds,
- sums usage and emits agent-facing `response.usage` plus
  `metadata.proxy_billed_usage`.

The downstream-WebSocket handler `proxy_responses_websocket`
(`app/modules/proxy/_service/websocket/mixin.py`) is a persistent, multiplexed
relay: one upstream WebSocket carries multiple pending turns, events are pushed
to the client live, and terminal handling / settlement live in
`_process_upstream_websocket_text` and `_finalize_websocket_request_state`.

## Decisions

### D1: Reuse the fold engine via an `open_round` adapter (do not re-implement)
For a continuation-eligible WebSocket turn, drive the existing fold engine with
an `open_round` that opens a round on the already-selected account (reusing
`_open_upstream_websocket` / the selected `Account`), sends the round payload,
reads `upstream.receive()` until a terminal event, converts each upstream text
message to an SSE block (`data: {json}\n\n`, matching how
`_process_upstream_websocket_text` already treats upstream text), and yields it.
The folded SSE output is parsed back and sent to the downstream client as
WebSocket frames. This reuses all tested buffering / index-rewriting / usage
logic and confines new code to the adapter + framing + settlement.

Rejected alternative — re-implement folding natively inside
`_process_upstream_websocket_text`: highest risk (the most complex function in
the system), duplicates the fold's buffering/index/usage logic, and multiplies
the documented settlement/continuity trapdoors.

### D2: Do not preemptively route eligible turns to the HTTP fold
`should_apply_codex_continuation` is true for essentially every reasoning
request, and truncation is only known after a round completes. Routing eligible
turns to the HTTP path preemptively would divert **all** reasoning traffic off
the WebSocket transport, forfeiting prewarm amortization and upstream
overload-absorption. Continuation must act only on turns that actually truncate,
which the fold engine already does.

### D3: Account/reservation reuse
The fold's hidden rounds run inside one already-admitted turn: they reuse the
selected `Account`, auth headers, route, and Codex client, and they do not
re-enter account selection or open new API-key reservations. This mirrors the
HTTP fold's `_open_continuation_round`.

### D4: Settlement (ship first, safe)
`_finalize_websocket_request_state` currently settles from
`event.response.usage`. Before folding can bill correctly it must prefer
`metadata.proxy_billed_usage` when present (mirroring
`_stream_usage_accounting` on the HTTP path). This is shipped first as an
isolated change: until a WebSocket event carries `metadata.proxy_billed_usage`
(only produced by the fold), the new branch is inert, so it is safe to deploy
ahead of the folding work.

### D5: Gating and rollout
A new setting `codex_continuation_websocket_enabled` (env
`CODEX_LB_CODEX_CONTINUATION_WEBSOCKET_ENABLED`) defaults to `false`. The
folding is enabled on live traffic only after synthetic-round tests pass and a
live validation window confirms `reasoning_tokens` no longer clusters on the
`518*n - 2` boundary. This keeps the live billing path unchanged until validated.

## Streaming-semantics tradeoff

Like the HTTP fold, the WebSocket fold buffers the final answer and re-chunks it
at round end rather than streaming it token-by-token live. For
continuation-eligible turns this changes final-answer delivery timing on the
WebSocket path. This is inherent to continuation folding and is accepted (it is
already the HTTP fold's behavior); the enable flag lets operators opt in
per-deployment.

## Risks

- Turn-loop integration: `proxy_responses_websocket` multiplexes pending turns
  over one upstream WebSocket; a folded turn opening its own rounds must not
  corrupt pending-request bookkeeping, keepalives, or reconnect/replay state.
- Prewarm / sticky affinity interaction with per-round connections.
- Client tolerance of buffered/re-chunked final answers over WebSocket.

These require synthetic-round integration tests and a gated live validation
window before the flag is enabled in production.
