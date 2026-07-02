# Tasks

## 1. Schema and migration

- [x] 1.1 Add `WebsocketContinuityStateRecord` to `app/db/models.py` (near
      `HttpBridgeSessionRecord`): PK `(session_key, api_key_id)` with
      `api_key_id` default/server-default `''`, `state: Text` (JSON-encoded),
      `updated_at: DateTime(timezone=True)` with `func.now()` default /
      server-default / onupdate; add
      `idx_websocket_continuity_states_updated_at` next to the other `Index()`
      declarations.
- [x] 1.2 Re-verify the current single Alembic head via `ScriptDirectory`,
      then author
      `app/db/alembic/versions/<YYYYMMDD_HHMMSS>_add_websocket_continuity_states.py`
      off it (revision = filename stem, policy pattern
      `^\d{8}_\d{6}_[a-z0-9_]+$`), copying the `_has_table` idempotence +
      full-downgrade pattern from `20260409_000000_add_http_bridge_sessions.py`.
- [x] 1.3 Verify `.venv/bin/python -m app.db.migrate upgrade head` then
      `.venv/bin/python -m app.db.migrate check` (that order) pass; confirm
      model↔migration parity via
      `tests/unit/test_db_migrate.py::test_schema_migration_contract_matches_after_upgrade`.

## 2. Repository and wiring

- [x] 2.1 Add `WebsocketContinuityStatesRepository`
      (`app/modules/proxy/continuity_repository.py`, modeled on
      `sticky_repository.py`): `get` (defensive `json.loads`, `None` on
      garbage), dialect-switched upsert (`pg_insert`/`sqlite_insert`
      `on_conflict_do_update`, wrapped in `retry_sqlite_write`), and
      `purge_before(cutoff)` (tz handling consistent with
      `DurableBridgeRepository.purge_closed_before`).
- [x] 2.2 Add `websocket_continuity: WebsocketContinuityStatesRepository | None
      = None` to `ProxyRepositories` (`repo_bundle.py`) and construct it in
      `_proxy_repo_context` (`app/dependencies.py`); default `None` keeps the
      existing test bundle constructions green.

## 3. State serialization

- [x] 3.1 Extend `_WebSocketContinuityState` (`support.py`) with non-persisted
      `persist_key: tuple[str, str] | None = None` (plus inflight/dirty
      ordering flags), `to_persistable_dict()`, `is_pristine()`, and a
      defensive `apply_persisted_dict()` that type-checks every field and
      re-applies the 8-alias cap.

## 4. Hydration read path

- [x] 4.1 Make `_websocket_continuity_state_for_request` (`mixin.py`) async:
      keep the LRU logic, set `persist_key` on keyed states (unkeyed states
      keep `None`), and on a fresh miss with a pristine state read the
      persisted row inside its own `_repo_factory()` scope and hydrate in
      place; wrap the whole DB block in try/except that logs a warning
      (hashed session id) and continues with the empty state.
- [x] 4.2 Update the single call site in `proxy_responses_websocket` to
      `await`.

## 5. Persistence write path

- [x] 5.1 Add `self._websocket_continuity_persist_tasks: set[asyncio.Task[None]]`
      to `ProxyService.__init__` and a
      `_schedule_websocket_continuity_persist(continuity_state)` helper:
      no-op when `persist_key is None`; snapshot the payload synchronously;
      per-state inflight/dirty serialization; task body opens its own
      `_repo_factory()` scope, None-guards the repository, upserts, and
      swallows exceptions with a warning; track the task with a
      discard-and-log done-callback; never await from the relay (no
      `asyncio.shield` copy from `_write_request_log`).
- [x] 5.2 Call it from both write sites in
      `_process_upstream_websocket_text`: the fold-terminal
      `response.completed` branch (after alias recording, before the branch
      returns) and the plain `response.completed` branch (after
      `_record_websocket_continuity_completion`).

## 6. Pruning

- [x] 6.1 Add `_WEBSOCKET_CONTINUITY_STATE_MAX_AGE_HOURS = 48` and a guarded
      `WebsocketContinuityStatesRepository(session).purge_before(...)` call to
      `StickySessionCleanupScheduler._cleanup_once`
      (`cleanup_scheduler.py`) so a missing table cannot break the existing
      sticky/bridge purges.

## 7. Facade

- [x] 7.1 Re-export the repository class and new helpers through
      `app/modules/proxy/service.py` so `_facade()` monkeypatching in tests
      keeps working.

## 8. Regression coverage

- [x] 8.1 Migration round-trip test in `tests/unit/test_db_migrate.py`
      (upgrade to parent, upgrade to new revision, insert asserting the
      `api_key_id` server-default `''`, table/index present, downgrade drops
      both).
- [x] 8.2 Convert `test_websocket_continuity_state_reuses_codex_session_scope`
      (`tests/unit/test_proxy_utils.py`) to async/await; inject a recording
      fake `websocket_continuity` repo into the `_RepoContext` bundle.
- [x] 8.3 Hydration tests: in-memory miss + persisted row hydrates all fields
      including `folded_response_id_aliases`; store read raising degrades to
      an empty state with a warning; affinity disabled / missing session id
      never touches the store and keeps `persist_key=None`; corrupt persisted
      payload is discarded.
- [x] 8.4 Persistence tests at the product path
      (`_process_upstream_websocket_text`): a plain `response.completed` and a
      fold-terminal completion each schedule exactly one upsert whose snapshot
      matches `_record_websocket_continuity_completion` results (fold variant
      includes the alias); an upsert that raises logs a warning and leaves the
      downstream text unchanged.
- [x] 8.5 Repository CRUD on a real session (upsert-insert, upsert-update
      advancing `updated_at`, get miss, `purge_before`).
- [x] 8.6 Cleanup tests in `tests/unit/test_sticky_session_cleanup_scheduler.py`:
      stale (>48h) rows purged, fresh rows survive, missing table does not
      crash the loop or skip the sticky purge.

## 9. Validation

- [x] 9.1 `.venv/bin/python -m ruff check` clean on touched files.
- [x] 9.2 Targeted pytest green: `tests/unit/test_db_migrate.py`,
      `tests/unit/test_proxy_utils.py`,
      `tests/unit/test_sticky_session_cleanup_scheduler.py` (known
      pre-existing `test_ring_membership.py` failure excluded).
- [x] 9.3 `.venv/bin/python -m app.db.migrate upgrade head` then
      `.venv/bin/python -m app.db.migrate check` pass.
- [x] 9.4 `openspec validate share-websocket-continuity-state --strict`
      passes.
