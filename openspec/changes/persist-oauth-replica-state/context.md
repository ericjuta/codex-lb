# Durable OAuth flow coordination context

## Purpose and scope

This change makes dashboard OAuth completion reliable when a browser callback, pasted callback, completion request, or status poll reaches a replica other than the one that started the flow. It also lets a pending browser flow survive an originating-process restart when another replica shares the same PostgreSQL database and encryption key.

## Rationale

The database is already the fork's coordination boundary for shared deployment state. Persisting only serializable OAuth metadata fits that model while keeping sockets and asyncio tasks local. Load-balancer affinity was rejected because it is not durable and cannot protect against process loss.

## Constraints

- PKCE verifiers are secrets and remain encrypted outside process memory.
- Every replica must use the same existing encryption key.
- SQLite remains supported for one process; the repository still uses atomic SQLite writes for deterministic tests and restart persistence.
- Account identity, reauthentication targeting, frontend behavior, and routing-cache policy remain unchanged.

## Failure modes

- An expired durable row invalidates a still-pending local verifier so an old authorization code is never exchanged.
- A callback loser whose error write is rejected because another replica committed success must report success after reconciliation.
- A superseded device poller that no longer owns the slot must save no account and write no terminal state.
- If the originating device poller exits, the flow times out and is retried rather than spawning duplicate cross-replica pollers.

## Concrete example

Replica A starts a browser flow and persists its encrypted verifier. The pasted callback reaches replica B, which decrypts the verifier, exchanges the code, saves the account, and records success. A later status poll reaches replica A; durable success replaces its stale local pending state, so the dashboard completes instead of polling forever.

## Operational notes

Deployment verification should use two processes against one PostgreSQL database with identical encryption keys. Migration verification must retain one Alembic head and exercise upgrade, downgrade, and re-upgrade. Normative behavior is defined in `specs/oauth-flow-coordination/spec.md`.
