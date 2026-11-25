# Design

## Context

`RuntimeState.error_count` and `cooldown_until` are one counter and one deadline per account. `select_account` excludes an account whose count reached three until `min(300, 30 * 2**(n-3))` seconds pass, and skips an account in cooldown. Every responses path writes them through `_handle_stream_error`, `record_errors`, `mark_temporary_cooldown` and `record_success`.

## Decisions

### The health write names the model

`_handle_stream_error`, `_handle_websocket_connect_error`, `LoadBalancer.record_error(s)`, `mark_temporary_cooldown` and `record_success` take a keyword `model`. Call sites pass the model the account was selected for: `payload.model` on the stream and compact paths, `request_state.model` on the websocket path, and the bridge session's model on the HTTP bridge. The parameter is explicit rather than a context variable because stream generators are stepped from more than one task, and a context variable set in one step is not visible in the next.

`model=None` keeps the account-wide behavior. Callers with no model (token refresh failover, file operations, transcription, Codex control) are unchanged.

### State and selection

`RuntimeState.model_health` maps a model key to `ModelHealth(error_count, last_error_at, cooldown_until)`. `_build_states` copies the requested model's entry onto three read-only `AccountState` fields (`model_error_count`, `model_last_error_at`, `model_cooldown_until`). `select_account` applies the same gates to them that it applies to the account-wide fields, puts a model-backed-off account in the same `in_error_backoff` list, and the backoff fallback compares the later of the two expiry times.

`select_account` never writes the model fields, so the write-back in `_sync_runtime_state` cannot leak one model's state into the account-wide fields or into another model. `_build_states` owns expiry: an elapsed cooldown or an elapsed backoff deletes the entry. Counts below three stay until that model succeeds on the account, which is what "consecutive" means for the account-wide counter too.

### What stays account-wide

`rate_limit`, `quota` and permanent failures describe the account's subscription or credentials. The stored health tier (`health_tier`, drain entry time, probe streak) also stays account-wide; a model's errors only raise the tier on the state built for that model's selection, and only when the account-wide tier is healthy.

### The handshake 403 keeps its health consequence

The first idea was to stop counting an empty-body handshake `403` at all. It is rejected. The `responses-api-compat` requirement "Pre-commit ambiguous websocket 403 failures fail over by account" makes that `403` an account-scoped failure with a cooldown, and the backoff it feeds is the only local brake on a handshake storm. What the `403` says about other models is unknown, so the consequence is narrowed to the model that observed it instead of removed.

### Bounds and keys

Model keys come from client requests. One account keeps at most 64 entries; inserting a 65th evicts the entry with the oldest error. Keys are trimmed and lower-cased, matching how HTTP bridge sessions compare models.

## Risks

- An account that is broken for every model is now found once per model: each model's traffic pays up to three failed attempts before its own backoff starts. Failover hides most of them from clients.
- The state is per worker process, as the account-wide counters already are.

## Rollback

Revert the change. There is no stored state to migrate.
