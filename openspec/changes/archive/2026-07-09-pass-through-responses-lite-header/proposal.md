## Why

Codex clients intentionally send `X-OpenAI-Internal-Codex-Responses-Lite` to request Responses Lite behavior, but codex-lb currently removes it before upstream forwarding. The proxy must preserve this client-selected behavior instead of disabling it.

## What Changes

- Preserve `X-OpenAI-Internal-Codex-Responses-Lite` when forwarding inbound requests upstream.
- Apply passthrough consistently to Responses HTTP, compact, internal WebSocket, and client-facing WebSocket transports.
- Preserve the GPT-5.6 Lite and Code Mode capability metadata in codex-lb's static bootstrap catalog so model discovery remains correct before a live catalog refresh.
- Replace regression tests that require stripping with tests that require preservation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `responses-api-compat`: Change the internal Responses Lite header contract from upstream removal to case-preserving passthrough.

## Impact

- Affects shared inbound header filtering and upstream header builders in `app/core/clients/proxy.py`.
- Affects the GPT-5.6 fallback entries in `app/core/openai/model_registry.py` and their `/backend-api/codex/models` representation.
- Changes the observable upstream request contract for clients that send the Responses Lite header.
- Upstream model compatibility errors are returned normally rather than preemptively disabling Lite behavior in codex-lb.
