# Design

## Context

`_WebSocketContinuityState` (`app/modules/proxy/_service/support.py`) is
looked up once per downstream WebSocket connection by
`_websocket_continuity_state_for_request` (`websocket/mixin.py`), keyed
`(session_id, api_key.id or None)` from
`_owner_lookup_session_id_from_headers`, and stored in the per-worker
`_websocket_continuity_index` LRU (cap 4096). It is written by
`_record_websocket_continuity_completion` at two sites inside
`_process_upstream_websocket_text`: the fold-terminal branch (which also
records the folded response-id alias) and the plain `response.completed`
branch. Neither write site has access to the connection headers or session
id — only to the state object itself.

Constraints:

- 8 uvicorn workers; no shared memory. The database (Postgres or SQLite) is
  the only shared store all workers already reach.
- The relay treats downstream latency as critical: nothing on the
  per-turn event path may block on the database.
- The schema-drift gate (`check_schema_drift`, compare_type=True,
  compare_server_default=True) and
  `test_schema_migration_contract_matches_after_upgrade` enforce exact
  model↔migration parity on both dialects.
- Workers can run before the migration lands (mid-rollout), and test repo
  bundles construct `ProxyRepositories` without the new field.

## Decisions

### 1. `Text` + `json.dumps` for the state column, not `JSON`/`JSONB`

The intended design said JSON/JSONB, but no JSON column exists anywhere in
`app/db/models.py`, and `sa.JSON` (or a JSONB variant) reflects differently
per dialect, risking `compare_type` drift-gate failures. `Text` storing a
JSON document has direct precedent (`HttpBridgeSessionRecord.latest_turn_state`,
`ApiKey.metadata_json`) and zero drift risk. The payload is small (five
fields, alias dict capped at 8) and never queried by content — only by key —
so a JSON column type buys nothing. This is a deliberate anti-drift deviation
from the initial intent. Rejected: `sa.JSON().with_variant(JSONB, "postgresql")`
unless a spike proves `migrate check` clean on both dialects; not worth the
risk for an opaque blob.

### 2. Hydrate once at connection setup, not per turn

`_websocket_continuity_state_for_request` becomes async and, on a fresh
in-memory miss, awaits a single repository read before the relay loop starts.
Its sole app call site (`proxy_responses_websocket`) runs once per downstream
connection, so the added round-trip is bounded by the pool timeout and never
touches per-turn latency. The websocket protocol declares the method as
`Any`, so the signature change is protocol-safe. Rejected: reading the store
on every turn (adds per-turn DB latency for no benefit — within a connection
the in-memory object is authoritative) and a write-through cache layer
(overengineering for a single-key blob).

### 3. Pristine-only hydration

The state object is inserted into the LRU before the awaited read completes,
so a concurrent connection on the same worker could already be recording
completions into it. Hydration therefore applies only when the state is still
pristine (all fields at defaults); otherwise the persisted row is discarded.
In-memory data is always at least as fresh as the store on the same worker.
Rejected: field-level merge of persisted and in-memory data — there is no
meaningful merge for anchor/fingerprint fields, and a wrong merge corrupts
retry-safety decisions.

### 4. Non-blocking snapshot writes with per-state ordering

Persistence mirrors the `_write_request_log` task pattern (tracked task set,
done-callback that discards and logs) but deliberately **without** the
`asyncio.shield` await: the relay must never wait on the store. The payload
is snapshotted synchronously at schedule time (`to_persistable_dict`) so a
later turn cannot mutate what an in-flight task writes. Per-state
inflight/dirty flags serialize writes for one state object, so an older
snapshot cannot overwrite a newer one within a worker. Each task opens its
own `_repo_factory()` scope — no `AsyncSession` is ever shared across tasks
(repo-wide async ownership rule). Rejected: synchronous upsert on the
completion path (blocks the relay), fire-and-forget untracked tasks (orphaned
failures), and reusing the relay's session (ownership violation).

### 5. Persistence key rides on the state object

The write sites have the state but not the headers, so the lookup sets a
non-persisted `persist_key: tuple[str, str] | None` on the state
(`(session_id, api_key_id or "")`). Unkeyed states — affinity disabled or no
session header — keep `persist_key=None` and are never persisted or hydrated.
Rejected: threading headers/session id through
`_process_upstream_websocket_text` (touches a wide call chain for one value).

### 6. Last-write-wins across workers

Two workers serving the same session concurrently (client reconnect race)
both upsert; the newest `updated_at` wins. A stale persisted anchor is safe:
upstream anchor invalidation already routes through the existing fail-closed
`stream_incomplete` full-history retry, so the worst case equals today's
behavior, never corruption. Rejected: row versioning or advisory locking —
cross-worker races are rare (a session speaks to one worker at a time) and
the failure mode is already absorbed.

### 7. Prune via the existing cleanup scheduler

`StickySessionCleanupScheduler._cleanup_once` is already leader-elected, runs
on a configured interval, opens its own background session, and purges
prompt-cache and closed-bridge rows. It gains a
`purge_before(utcnow() - 48h)` call with its own guard so a missing table
(mid-rollout) cannot break the existing purges. Rejected: a new dedicated
scheduler (duplicate leader election and lifecycle for one DELETE) and a TTL
column (updated_at + cutoff is sufficient).

### 8. Optional repository field, guarded touchpoints

`ProxyRepositories.websocket_continuity` defaults to `None`, keeping the 11
existing test-site constructions valid. Every touchpoint (hydrate, persist,
purge) None-guards and wraps DB work in try/except that logs a warning and
continues — the store is an accelerator, not a dependency. Log lines use
hashed session identifiers (`_hash_identifier` pattern from
`observability.py`); raw session keys never reach logs.

## Risks / Trade-offs

- **Connection-setup latency on a slow database**: hydration adds one awaited
  read at WebSocket accept. Bounded by pool timeout; failure degrades to an
  empty state. Accepted because it is once per connection, not per turn.
- **Async signature change**: a missed `await` on
  `_websocket_continuity_state_for_request` silently yields a coroutine. The
  single app call site and the three sync test calls are updated together;
  ruff + pytest gate the change.
- **Widened write volume**: one background upsert per completed turn. SQLite
  writes go through `retry_sqlite_write`; the payload is a tiny blob keyed by
  primary key, and pruning bounds table growth at ~48h of active sessions.
- **Merge-head churn**: this repo accretes parallel Alembic heads quickly.
  The single head must be re-verified via `ScriptDirectory` immediately
  before authoring the revision, then `upgrade head` + `migrate check` run in
  that order.
