## ADDED Requirements

### Requirement: WebSocket Continuity State Is Persisted To A Shared Store
codex-lb MUST persist a session's WebSocket continuity state — last completed
input count, last completed response id, last completed input-prefix
fingerprint, pending function-call ids, and folded response-id aliases — to a
shared `websocket_continuity_states` store keyed by
`(session_key, api_key_id)` (empty string when no API key), after each
recorded continuity completion: both the plain `response.completed` path and
the fold-terminal path, where the persisted snapshot MUST include any
just-recorded folded response-id alias. States without a continuity key
(codex session affinity disabled, or no session id derivable from the
connection headers) MUST NOT be persisted.

#### Scenario: Plain completion persists the continuity snapshot
- **WHEN** a keyed WebSocket turn completes with `response.completed` and the
  continuity completion is recorded
- **THEN** codex-lb schedules exactly one upsert of the state snapshot to the
  shared store under the session's `(session_key, api_key_id)` key

#### Scenario: Fold terminal persists the alias with the snapshot
- **WHEN** a folded WebSocket turn completes and records a
  `visible_id -> final_round_upstream_id` alias on the continuity state
- **THEN** the persisted snapshot includes that alias in
  `folded_response_id_aliases`

#### Scenario: Unkeyed states are never persisted
- **WHEN** a WebSocket connection has codex session affinity disabled or no
  session id in its headers
- **THEN** no read from or write to the shared store occurs for that
  connection's continuity state

### Requirement: WebSocket Connections Hydrate Continuity State On Setup
codex-lb MUST, when a downstream WebSocket connection's continuity lookup
misses the worker's in-memory index, attempt to hydrate the freshly created
state from the shared store exactly once at connection setup, before the
relay loop starts. Hydration MUST apply only while the state is pristine
(all fields at defaults) so persisted data can never overwrite fresher
in-memory data, and hydrated fields MUST be defensively validated (including
re-applying the folded-alias bound) before use. A lookup that hits the
in-memory index MUST NOT read the store.

#### Scenario: Cross-worker reconnect restores the folded alias
- **WHEN** a client whose folded turn completed on worker A reconnects to
  worker B, whose in-memory index has no entry for the session
- **AND** the shared store holds the session's persisted continuity state
- **THEN** worker B hydrates the state at connection setup, including
  `folded_response_id_aliases`
- **AND** a follow-up turn sending the folded (visible) response id as
  `previous_response_id` is rewritten to the final hidden round's upstream id
  without a fail-closed retry

#### Scenario: In-memory hit skips the store
- **WHEN** the connection's continuity lookup finds an existing state in the
  worker's in-memory index
- **THEN** no store read is performed and the in-memory state is used as-is

### Requirement: Continuity-State Persistence Never Blocks The Relay
Continuity-state persistence MUST be best-effort and non-blocking: writes
MUST run as tracked background tasks that the relay never awaits, each task
MUST open its own database session scope (never sharing a session with the
relay or another task), and the persisted payload MUST be snapshotted
synchronously at schedule time so later turns cannot mutate an in-flight
write. Within a worker, writes for one state MUST be ordered such that an
older snapshot never overwrites a newer one. Task failures MUST be logged
via the task set's completion handling, not raised into the relay.

#### Scenario: The relay does not wait for the store
- **WHEN** a continuity completion schedules a persistence write
- **THEN** the downstream terminal event is delivered without awaiting the
  write

#### Scenario: A failed write does not disturb the turn
- **WHEN** the background upsert raises (for example, the database is
  unavailable)
- **THEN** a warning is logged and the downstream event text is unchanged
- **AND** the in-memory continuity state remains authoritative for the
  connection

### Requirement: Continuity Store Failures Degrade To In-Memory Behavior
Any failure of the shared continuity-state store MUST degrade to the
per-worker in-memory-only behavior that exists today and MUST NOT fail the
WebSocket relay: a missing table (mid-rollout), an unavailable database, an
absent repository binding, and a corrupt or non-conforming persisted payload
MUST each result in a warning and an empty (or unhydrated) state. Warning
log lines MUST NOT contain raw session identifiers; identifiers MUST be
hashed following the existing continuity observability convention. Stale
persisted data read by another worker MUST be recoverable through the
existing fail-closed continuity retry, never through corruption of the turn.

#### Scenario: Hydration read failure yields an empty state
- **WHEN** the store read at connection setup raises
- **THEN** a warning is logged with a hashed session identifier
- **AND** the connection proceeds with a fresh empty continuity state and the
  relay operates exactly as it does today

#### Scenario: Corrupt persisted payload is discarded
- **WHEN** the persisted row's payload fails JSON decoding or field
  validation
- **THEN** hydration is skipped and the connection proceeds with the empty
  state

#### Scenario: Absent repository skips the store entirely
- **WHEN** the repository bundle provides no continuity-state repository
  (for example, before the migration lands)
- **THEN** hydration and persistence are skipped without error
