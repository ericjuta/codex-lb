## Context

Codex remote compaction v2 returns an opaque encrypted compaction payload. Current Codex-affinity normalization extracts only `type` and `encrypted_content`, even when the upstream output item also carries an `id`. Codex clients with response item IDs enabled then assign a new `cmp_...` ID at the durable-history boundary and resend the unchanged encrypted payload under that new identity. Upstream rejects the pair because the encrypted content is bound to the original item ID.

The same normalization helper feeds both direct Codex compact JSON responses and the synthetic SSE stream used for terminal `compaction_trigger` requests.

## Goals / Non-Goals

**Goals:**

- Preserve a valid upstream compaction item ID with its encrypted content.
- Keep the direct compact and terminal-trigger stream contracts identical.
- Prevent Codex clients from inventing IDs for opaque compaction items when a provider omits the ID.
- Add regression coverage at both repositories' externally failing request paths.

**Non-Goals:**

- Change public OpenAI-style `/v1/responses/compact` behavior.
- Preserve arbitrary historical output items from remote compaction.
- Invent a proxy-side compaction ID when upstream provides none.
- Change account selection, compact retry, or encrypted-content handling.

## Decisions

1. The codex-lb normalizer will copy a non-empty string `id` from the selected upstream compaction item into the canonical `{"type": "compaction", "encrypted_content": ...}` result.
   - This keeps the existing single-item canonical shape while preserving the identity required to reuse opaque encrypted content.
   - Reconstructing a new ID in codex-lb was rejected because the proxy cannot re-encrypt the payload for that identity.

2. The legacy `compaction_summary` fallback will remain ID-less unless that summary mapping explicitly carries a non-empty ID.
   - Missing identity is preferable to invented identity because current Codex clients can submit ID-less compaction items.
   - Requiring an ID was rejected because older upstream compact shapes may omit one.

3. Both Codex compact response surfaces will continue using the shared normalization helper.
   - The synthetic SSE `response.output_item.done` item and terminal `response.completed.response.output` item will therefore contain the same optional ID.
   - Separate route-specific normalization was rejected because it would allow the contracts to drift again.

4. The adjacent Codex client will retain real upstream `cmp_` IDs but will not synthesize a missing ID for `Compaction` or `ContextCompaction` response items.
   - This is defense in depth for providers and proxies that return encrypted compaction content without identity.
   - Removing all compaction IDs from requests was rejected because it would discard correct upstream identity.

## Risks / Trade-offs

- [Risk] A downstream consumer may have assumed normalized compaction items never contain `id`. -> Mitigation: the field is optional in the Responses item contract, and focused route tests will prove unchanged behavior when upstream omits it.
- [Risk] An upstream sends an empty or non-string ID. -> Mitigation: preserve only non-empty strings and otherwise keep the existing ID-less behavior.
- [Risk] Client hardening could suppress IDs beyond encrypted compaction output. -> Mitigation: special-case only missing IDs on the two compaction variants; preserve and validate IDs that were actually supplied.

## Migration Plan

Deploy the codex-lb preservation change and rebuild the running image. Rebuild the adjacent Codex client with the missing-ID guard. Existing poisoned rollouts retain their synthesized ID, so operators should begin a fresh session or disable item IDs before resuming those rollouts. Rollback is a source revert; no database or schema migration is required.

## Open Questions

None.
