## Context

The fork already persists durable bridge ownership, the latest response ID, and a verified input-prefix fingerprint. On a hard-affinity reattach with no live local session or forwardable owner, `streaming.py` injects that response ID and trims the verified prefix. This is correct for incremental continuations, but it can strand a complete client full resend on an eventless fresh upstream WebSocket.

Upstream fixed this in `b5a515f0`, but that commit assumes the account-neutral replay module and load-balancer decomposition introduced by `#1437`. This fork explicitly did not adopt those routing changes, so the port must remain inside the existing durable hard-affinity path.

## Goals / Non-Goals

**Goals:**

- Prove, fail closed, when a verified full resend already contains sufficient prior response context.
- Preserve that request unanchored on the original durable account for the first fresh bridge submission.
- Persist an exact, response-bound manifest of direct tool calls needed to prove a tool-loop resend.
- Preserve current anchor injection for all ambiguous, legacy, malformed, or incomplete states.

**Non-Goals:**

- Moving requests across accounts or introducing account-neutral replay.
- Changing owner-forward failure recovery, live-session trimming, client-supplied anchors, or public schemas.
- Importing upstream's `_load_balancer/`, `session_registry.py`, or full replay-safety decomposition.

## Decisions

### Decision: add a focused pure replay-proof module

A small proxy helper module will project response-owned bookkeeping from a verified prefix and classify two safe suffix shapes: retained completed assistant output followed by fresh input, or exact direct tool call/output settlement. The module will expose typed, side-effect-free functions and fail closed on unknown item shapes, duplicate IDs, invalid status/order, or unsupported client-settled call types.

Alternative: copy upstream `replay_safety.py` wholesale. Rejected because most of that module exists to support cross-account replay from `#1437`, which is outside this fork's routing contract.

### Decision: bind the durable manifest to the response ID

`http_bridge_sessions` will gain one nullable text column containing canonical JSON with `{response_id, calls}`. Repository readers return a manifest only when the embedded response ID matches `latest_response_id` and every key/value is a nonblank string. Every write that advances or clears the response ID must atomically replace or clear the manifest.

Alternative: persist a second relational table. Rejected because the manifest is small, replaced atomically with one response alias, and never queried independently.

### Decision: reconcile added, done, and terminal output before persistence

Request state will track tool-call `output_item.added` and `output_item.done` maps separately. A manifest is known only when both maps match exactly and terminal `response.completed.output` either repeats that same complete map or contains no tool calls. Duplicates, mismatches, malformed events, `computer_call`, and `mcp_approval_request` invalidate the entire manifest.

### Decision: skip both durable and session-level anchor injection for the proven request

Classification occurs before durable anchor injection. A safe full resend retains hard affinity and the durable preferred account, but leaves `previous_response_id` absent. The newly created session is not seeded with the old durable response before its first request, preventing session-level injection from undoing the decision. Once the response completes, ordinary live continuity resumes.

## Risks / Trade-offs

- [False-positive replay proof] → Require exact prefix fingerprint, strict suffix ordering, complete manifest equality, and fail-closed parsing.
- [Rolling-upgrade stale manifest] → Embed the response ID and reject mismatches.
- [Migration graph divergence] → Base the new revision on the fork's live Alembic head and run upgrade/check plus repository round-trip tests.
- [Large bridge regression surface] → Add pure helper tests, repository tests, focused bridge tests, and a public `/v1/responses` regression.

## Migration Plan

1. Add the nullable manifest column at the current single Alembic head; no backfill is required.
2. Deploy writers/readers together. Existing rows decode as unknown and retain anchored behavior.
3. On rollback, remove the nullable column; runtime behavior returns to unconditional durable-anchor injection.

## Open Questions

None.
