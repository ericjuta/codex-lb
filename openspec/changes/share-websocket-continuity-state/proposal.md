# Share WebSocket Continuity State Across Workers

## Why

The WebSocket continuity state (`_WebSocketContinuityState`) — last completed
response id, input count, input-prefix fingerprint, pending function-call ids,
and the folded response-id aliases shipped in
`fix-ws-fold-previous-response-chaining` — lives in a **per-worker in-memory
LRU** (`_websocket_continuity_index`, cap 4096). The deployment runs **8
uvicorn workers**, so a client that reconnects and lands on a different worker
loses all of it:

1. A folded turn's `visible_id -> final_round_upstream_id` alias is gone, so a
   follow-up sending the folded (visible) id as `previous_response_id` misses
   the transparent rewrite and falls into the fail-closed
   `stream_incomplete` retry — one extra full-history round-trip on ~7/8 of
   reconnects instead of a transparent fast path.
2. `last_pending_function_call_ids` is gone, so interrupted-tool-output
   injection cannot synthesize outputs for calls the client abandoned,
   surfacing upstream `"No tool output found for function call ..."` errors
   that the fail-closed path must absorb.
3. `last_completed_input_count` / `last_completed_input_prefix_fingerprint`
   are gone, so retry-safety trimming and full-resend detection restart cold.

The `fix-ws-fold-previous-response-chaining` design rejected persistence at
the time as disproportionate for the alias alone; with the whole continuity
state now load-bearing for chaining correctness, the cross-worker miss is the
dominant residual failure mode. This change shares the state through the
database that all workers already use.

## What Changes

- **New table `websocket_continuity_states`** (Alembic migration off the
  current single head): primary key `(session_key, api_key_id)` with
  `api_key_id` server-default `''`, a `state` column holding the JSON-encoded
  continuity fields (`Text`, following the `latest_turn_state` precedent), and
  an indexed timezone-aware `updated_at`.
- **New repository** `WebsocketContinuityStatesRepository`
  (`app/modules/proxy/continuity_repository.py`): `get`, dialect-switched
  upsert (`on_conflict_do_update`, wrapped in `retry_sqlite_write`), and
  `purge_before`. Wired into `ProxyRepositories` as an optional field
  (default `None` keeps existing test bundles valid).
- **Hydration at connection setup**: `_websocket_continuity_state_for_request`
  becomes async; when the in-memory index misses and the freshly created state
  is pristine, it reads the persisted row once (own repository scope) and
  hydrates the state in place with defensive field validation. Runs once per
  downstream WebSocket connection, before the relay loop.
- **Best-effort, non-blocking persistence**: after each recorded continuity
  completion — both the plain `response.completed` path and the fold-terminal
  path (including a just-recorded folded response-id alias) — the relay
  snapshots the state synchronously and schedules a tracked background task
  that upserts it in its own session scope. The relay never awaits the write;
  per-state inflight/dirty flags keep within-worker snapshots ordered.
- **Degradation**: any store failure (missing table mid-rollout, unavailable
  database, absent repository, corrupt row payload) logs a warning and falls
  back to today's per-worker in-memory-only behavior. The relay never fails
  because of the store. Log lines carry hashed session identifiers only.
- **Pruning**: the existing leader-elected
  `StickySessionCleanupScheduler._cleanup_once` additionally purges
  `websocket_continuity_states` rows older than 48 hours; a missing table
  must not break the sticky/bridge purges already in the loop.

Cross-worker writes are last-write-wins by design: a stale persisted anchor
routes through the existing fail-closed/full-history retry, so the worst case
equals today's behavior — never corruption.

## Impact

- Affected specs: `codexcont-continuation-middleware` (shared continuity
  store: persistence, hydration, non-blocking writes, degradation),
  `sticky-session-operations` (cleanup-loop pruning).
- Affected code: `app/db/models.py`, new Alembic revision under
  `app/db/alembic/versions/`, `app/modules/proxy/continuity_repository.py`
  (new), `app/modules/proxy/repo_bundle.py`, `app/dependencies.py`,
  `app/modules/proxy/_service/support.py`,
  `app/modules/proxy/_service/websocket/mixin.py`,
  `app/modules/proxy/service.py` (facade re-exports, task-set init),
  `app/modules/sticky_sessions/cleanup_scheduler.py`.
- Schema change: one new table + migration (hard OpenSpec gate). No
  API-surface, routing, or configuration changes.
- Performance: one awaited DB read per downstream WebSocket **connection**
  (setup only, never per turn); one background write per completed turn.
- Folded tool-call turns now chain transparently across worker reconnects
  instead of paying the fail-closed retry; interrupted-tool-output injection
  and retry-safety trimming survive worker changes.
