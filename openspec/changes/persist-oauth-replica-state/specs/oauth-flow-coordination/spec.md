## ADDED Requirements

### Requirement: OAuth flow metadata is durable across replicas

The dashboard OAuth service SHALL persist browser and device flow metadata in the database keyed by flow id so that status, completion, browser callback, and manual callback requests can be served by a replica that did not originate the flow. The PKCE code verifier MUST be encrypted at rest with the existing account-token encryption key. Pending flows MUST carry an expiry and MUST be treated as absent after that expiry on every replica, including a replica that still has local pending state.

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

Every externally reachable OAuth entry point MUST reconcile durable state before acting on local state. A durable success MUST NOT regress to error. When an attempted error write is rejected because durable success already exists, the caller MUST leave local state non-error, reconcile, and report success without replaying the consumed authorization code.

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
