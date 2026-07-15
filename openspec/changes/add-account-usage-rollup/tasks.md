## 1. Schema & migration

- [x] 1.1 Add `AccountUsageRollup` and `AccountUsageRollupState` models to `app/db/models.py`: per-account BIGINT/float sums plus one seeded global `folded_through` watermark row
- [x] 1.2 Add an Alembic migration on the current single head creating `account_usage_rollups` and `account_usage_rollup_state`; seed the state row; downgrade drops both tables; verify upgrade/downgrade on both backends

## 2. Repository & read path

- [x] 2.1 Add rollup repository helpers: read all rollup sums plus the global watermark in one snapshot, upsert-add sums for a fold window, and delete by account
- [x] 2.2 Rewrite `AccountsRepository.list_request_usage_summary_by_account` to merge rollup sums with the dedupe aggregate constrained to `requested_at > folded_through` (fall back to full-history aggregate when no rollup rows exist); keep signature, filters, and post-merge cached clamp
- [x] 2.3 Delete the account's rollup row inside `AccountsRepository.delete` (both `delete_history` variants, same transaction)

## 3. Fold job

- [x] 3.1 Implement the fold pass: lock and re-read the seeded state row, aggregate `(watermark, now - 24h]` with dedupe and warmup/deleted filters, upsert sums, advance `folded_through`, and slice initial backfill into bounded requested-at windows (<=7 days per transaction)
- [x] 3.2 Add `build_account_usage_rollup_scheduler()` (15-min cadence) following the existing scheduler pattern, gated by `LeaderElection`, using the background session factory; start/stop it in `app/main.py` lifespan

## 4. Tests

- [x] 4.1 Unit/integration: folded + tail totals equal legacy full aggregate, including duplicate `(account_id, request_id, requested_at)` groups on both sides of folding and the pre-first-fold fallback
- [x] 4.2 Fold pass tests: safety-lag boundary excludes young rows; repeat invocation folds nothing new (idempotence); sliced backfill converges and reads stay correct mid-backfill
- [x] 4.3 Lifecycle test: account deletion (both variants) removes the rollup row and summaries drop the account
- [x] 4.4 Regression at the product path: `GET /api/accounts` returns unchanged usage summary values before/after folding (extend `tests/integration/test_accounts_api_extended.py` request-usage cases)

## 5. Validation & docs

- [x] 5.1 Update `openspec/specs/query-caching/context.md` with rollup rationale, fold cadence/lag constants, and the operator escape hatch (delete all rollup rows and the state row together to force re-backfill)
- [x] 5.2 Run `openspec validate --specs`, `uv run ruff check`, `uv run pytest` for touched areas on both SQLite and Postgres fixtures
