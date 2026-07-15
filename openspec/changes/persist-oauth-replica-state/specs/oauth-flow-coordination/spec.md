## ADDED Requirements

### Requirement: OAuth flow metadata is durable across replicas

The dashboard OAuth service SHALL persist browser and device flow metadata in the database keyed by flow id so that status, completion, browser callback, and manual callback requests can be served by a replica that did not originate the flow. Status and completion requests that omit a flow id MUST resolve the process-local current flow id and reconcile that targeted flow from durable storage before returning. The PKCE code verifier MUST be encrypted at rest with the existing account-token encryption key. Pending flows MUST carry an expiry and MUST be treated as absent after that expiry on every replica, including a replica that still has local pending state. A process-local callback listener MUST remain active while any non-expired pending browser flow exists in durable storage, even when that flow is absent from the listener owner's local store. Every non-forced listener shutdown path MUST use the same durable liveness guard, and a listener owner MUST revalidate durable liveness after releasing its socket so a flow created during shutdown is not stranded.

#### Scenario: Callback completes on another replica

- **GIVEN** replica A starts and persists a browser OAuth flow
- **WHEN** its browser or manual callback reaches replica B
- **THEN** replica B loads the durable flow, decrypts the verifier, and completes the exchange
- **AND** the durable flow records the terminal result

#### Scenario: Status observes another replica's terminal result

- **GIVEN** replica A still holds a flow locally as pending
- **AND** replica B has recorded durable success or error
- **WHEN** status or complete is served by replica A
- **THEN** replica A returns the durable terminal result and reconciles its local state

#### Scenario: Unscoped status and completion reconcile the current flow

- **GIVEN** replica A's local store identifies a current pending flow
- **AND** replica B has recorded that flow's durable terminal result
- **WHEN** status or complete reaches replica A without a flow id
- **THEN** replica A resolves its local current flow id and returns the durable terminal result

#### Scenario: Durable pending flow keeps a callback listener active

- **GIVEN** replica A owns a callback listener and has no local pending browser flow
- **AND** durable storage contains a non-expired pending browser flow created by another replica
- **WHEN** replica A evaluates whether the listener is idle
- **THEN** replica A keeps the listener active

#### Scenario: Flow created during listener shutdown remains reachable

- **GIVEN** replica A has determined that its callback listener is idle and has begun stopping it
- **WHEN** replica B durably creates a browser flow before replica A releases the callback socket
- **THEN** replica A revalidates durable liveness after shutdown and restores a listener

#### Scenario: Existing-account shortcut preserves remote listener liveness

- **GIVEN** durable storage contains a pending browser flow owned by another replica
- **AND** replica A has an existing account and owns the callback listener
- **WHEN** replica A receives an unforced OAuth start request
- **THEN** replica A does not bypass the durable listener-liveness guard

#### Scenario: Expiry invalidates an originating replica's local verifier

- **GIVEN** a pending flow is expired in durable storage while its origin replica still holds the verifier
- **WHEN** a callback reaches that origin replica
- **THEN** the callback is rejected without exchanging the authorization code
- **AND** the stale local flow is removed

### Requirement: Device OAuth completion is owned by one atomic slot

The service SHALL coordinate the current device OAuth flow through one database slot claimed atomically. Only the originating poller that atomically consumes the current slot MAY persist an account or write success or error. A superseded or duplicate poller MUST write neither account data nor terminal flow state. A non-originating completion request MUST report durable status and MUST NOT start a second poller.

#### Scenario: Concurrent device starts leave one current flow

- **WHEN** two replicas start device OAuth concurrently
- **THEN** the shared slot identifies exactly one current flow
- **AND** only that flow's originating poller can consume the slot and persist

#### Scenario: Overlapping starts on one replica preserve the later flow

- **GIVEN** an earlier device start is waiting for durable persistence
- **WHEN** a later start on the same replica supersedes it and claims the slot
- **THEN** the earlier start does not replace the later slot claim
- **AND** only the later start launches a poller

#### Scenario: Superseded poller cannot persist

- **GIVEN** a later device start has replaced the slot owner
- **WHEN** the earlier poller receives tokens or an OAuth error
- **THEN** its conditional slot consume fails
- **AND** it saves no account and writes no terminal status

#### Scenario: Non-originating completion does not duplicate polling

- **GIVEN** a device flow is being polled by its originating process
- **WHEN** a targeted completion request reaches another replica
- **THEN** that replica reports durable status without starting a poll task

### Requirement: Durable terminal status is monotonic and authoritative

Every externally reachable OAuth entry point MUST reconcile durable state before acting on local state. A durable success MUST NOT regress to error. When an attempted error write is rejected because durable success already exists, the caller MUST leave local state non-error, reconcile, and report success without replaying the consumed authorization code. Before saving account tokens, a callback or device poller MUST atomically claim a live pending flow for completion. If the durable row is missing, expired, or already claimed, that worker MUST NOT save account tokens or expose a new local success. A claimed completion MUST finalize durable success before local success is exposed; an intermediate completion claim MUST be reported externally as pending.

#### Scenario: Duplicate callback does not replay a consumed code

- **GIVEN** another replica completed the flow and recorded success
- **WHEN** a duplicate browser or manual callback reaches a replica with stale local pending state
- **THEN** the replica reports durable success
- **AND** it does not exchange the authorization code again

#### Scenario: Losing callback honors durable success

- **GIVEN** two callbacks race and the winner records durable success
- **WHEN** the losing exchange fails and its conditional error write is rejected
- **THEN** the loser reports the durable success
- **AND** it does not leave the local flow in error

#### Scenario: Flow expires while credentials are exchanged

- **GIVEN** a callback or device poller has exchanged credentials for a pending flow
- **WHEN** the durable flow expires or is purged before completion is claimed
- **THEN** the worker does not save the account tokens
- **AND** the worker does not report or cache an uncoordinated success
