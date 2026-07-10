## Why

Codex remote compaction can return encrypted content bound to an upstream compaction item ID. codex-lb currently discards that ID while normalizing the result, causing clients with response item IDs enabled to invent a replacement ID and receive persistent `invalid_encrypted_content` 400 responses.

## What Changes

- Preserve a non-empty upstream compaction item `id` when normalizing Codex-affinity compact results.
- Emit the preserved item unchanged through both terminal `compaction_trigger` SSE responses and direct `/backend-api/codex/responses/compact` JSON responses.
- Keep the existing canonical `type: "compaction"` normalization and single-item output contract.
- Add regression coverage proving the encrypted content and its upstream ID remain paired across both Codex compact surfaces.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `responses-api-compat`: Codex-affinity compaction normalization must preserve upstream compaction item identity alongside encrypted content.

## Impact

- Affects `app/modules/proxy/api.py` compaction-result normalization.
- Updates unit and integration coverage for the Codex terminal-trigger and direct compact response contracts.
- Restores compatibility with Codex clients that persist and resend response item IDs; public OpenAI-style compact behavior remains unchanged.
