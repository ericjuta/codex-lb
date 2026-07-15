## Context

`OAuthStateStore` keeps flow metadata, PKCE verifiers, callback-server handles, and device poll tasks in one process-local map. The runtime handles cannot be serialized, but the metadata needed by callbacks and status endpoints can. In a load-balanced PostgreSQL deployment, externally reachable OAuth requests may land on any replica, while a process restart may erase the only copy of a pending verifier.

The fork does not yet include upstream's targeted Team-seat reauthentication or routing-cache propagation changes. This change therefore adapts the durable coordination mechanism to the fork's existing add-account and reauthentication behavior without importing either unrelated policy.

## Goals / Non-Goals

**Goals:**

- Make persisted OAuth metadata the authority for every externally reachable flow entry point.
- Encrypt PKCE verifiers at rest with the existing `TokenEncryptor`.
- Keep success sticky under concurrent callback and device-poller races.
- Guarantee one current device flow and one authorized account-persist path across replicas.
- Preserve SQLite single-process support and the fork's existing OAuth API schemas.

**Non-Goals:**

- Change account identity matching or add targeted Team-seat reauthentication.
- Add routing-cache propagation beyond the fork's existing invalidation behavior.
- Make callback-server sockets or asyncio poll tasks transferable between processes.
- Change dashboard UI, OAuth provider configuration, or callback ports.

## Decisions

### Persist serializable flow state while retaining local runtime handles

A new repository stores flow id, state token, method, status, encrypted verifier, device metadata, expiry, and terminal timestamps. The local store remains only for callback-server and poll-task ownership plus a same-process cache. Sticky sessions were rejected because they do not survive process restarts and are operator-dependent.

### Reconcile before every externally reachable decision

Status, complete, manual callback, and browser callback paths read durable state before trusting local pending state. A durable terminal overrides local pending; a missing or expired durable row removes stale local state; a durable pending row may hydrate a replica that did not originate the flow.

### Make terminal writes monotonic in SQL

Status updates use one conditional SQL `UPDATE`. A non-success terminal cannot overwrite success, and callers must honor a rejected error write by reconciling and returning the durable success. A client-side read-then-write guard was rejected because separate sessions can race after both read pending.

### Use one atomic device-flow slot

A fixed database slot is claimed with a dialect-specific UPSERT and consumed with a conditional DELETE immediately before tokens are persisted. Only the poller that consumes the current slot may save an account or write a terminal status. The originating process remains the sole device poller; a non-originating `complete` call reports durable status without starting another poller for the single-use code.

### Add one fork-parented migration

One new revision creates both coordination tables and is parented directly on the fork's current single Alembic head. Combining the tables avoids importing upstream revision ancestry that does not exist in this fork.

## Risks / Trade-offs

- **Originating device poller exits mid-flow** -> The durable flow expires and the operator retries; another replica does not re-poll a single-use code.
- **Additional database I/O on OAuth endpoints** -> OAuth is operator-driven and low-volume; correctness is preferred over a process-local fast path.
- **Replicas use different encryption keys** -> Existing startup fingerprint enforcement remains the deployment guard; verifier decryption fails fast rather than falling back to plaintext.
- **Concurrent starts leave abandoned pending records** -> The slot selects one current device flow and opportunistic purge bounds expired and terminal history.

## Migration Plan

1. Apply the new revision after the current fork head; both tables start empty.
2. Existing in-flight process-local flows continue only on their originating process and naturally expire.
3. New flows persist immediately and use durable reconciliation.
4. Rollback drops the slot table first and then the flow-state indexes/table; no account-token data is removed.

## Open Questions

None.
