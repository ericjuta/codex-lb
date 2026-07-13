## Context

`enforce_context_window` (app/modules/proxy/request_policy.py) rejects estimable payloads at >=90% of the effective model window. It is invoked on three paths before compaction-trigger detection:

- `_stream_responses` (app/modules/proxy/api.py:2845) — runs before `strip_terminal_compaction_trigger_input` at :2849
- `_collect_responses` (app/modules/proxy/api.py:3080)
- websocket `_prepare_websocket_response_create_request` (app/modules/proxy/_service/websocket/mixin.py:1656) — has no trigger handling at all

Codex CLI recovery for `context_length_exceeded` sends a `/responses` turn with a terminal `compaction_trigger` item (bounded by `MAX_CONTEXT_WINDOW_COMPACTION_RETRIES_PER_TURN=3`). Because the recovery payload carries the full oversized history, it always trips the guard, deadlocking the client.

## Goals / Non-Goals

**Goals:**
- Well-formed compaction-lane requests (terminal `compaction_trigger`) bypass the guard on all three paths.
- Malformed trigger placement keeps its existing fail-closed 400.
- No behavior change for non-compaction requests.

**Non-Goals:**
- Changing the guard ratio or estimation method.
- Changing the standalone `/responses/compact` route (already unguarded).
- Codex CLI changes.

## Decisions

- **Detect, don't strip, inside the guard.** Add a `_has_terminal_compaction_trigger(payload)` check at the top of `enforce_context_window` and return early. Detection reuses the same shape rule as `strip_terminal_compaction_trigger_input` (single trigger, final top-level item) but does not mutate or raise; malformed placements fall through to the guard and are later rejected by the existing strip validation on the codex-affinity path. This keeps call sites unchanged and covers HTTP + WS uniformly.
- **Guard stays where it is in call order.** Reordering strip-before-guard in `api.py` would fix only the codex-affinity HTTP path; the WS path never strips. A guard-level exemption fixes all paths with one change.
- **Compact request size is bounded upstream.** The upstream compact endpoint accepts full histories by design; letting the oversized payload through on the compaction lane restores the pre-guard recovery contract.

## Risks / Trade-offs

- A client could append a trigger merely to bypass the guard — accepted: the payload is then processed as a compaction request (or fails upstream), not as a normal turn, so there is no guard-evasion value.
- WS path exemption relies on raw-payload shape before normalization; mitigated by checking the normalized `ResponsesRequest.input` (same object passed to the guard today).
