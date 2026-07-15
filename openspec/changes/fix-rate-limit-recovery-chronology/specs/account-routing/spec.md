## ADDED Requirements

### Requirement: Local rate-limit recovery preserves exact event chronology

When the process that observed the current upstream rate limit evaluates fresh-usage early recovery, it MUST compare usage evidence with that process's precise runtime block timestamp. Usage recorded before or at the exact runtime block timestamp MUST NOT reactivate the account, even when the usage timestamp is newer than the whole-second persisted `blocked_at` value. Usage recorded strictly after the exact runtime block timestamp MAY use the existing early-recovery path.

While the account remains `RATE_LIMITED`, synchronizing derived selection state back into worker runtime state MUST NOT replace a current precise runtime block marker with an equal-or-older persisted marker. The precise marker MUST remain authoritative across repeated selection passes.

Processes without a matching current runtime block marker MUST continue to enforce the persisted cooldown contract.

#### Scenario: Same-second pre-block usage does not recover the account

- **GIVEN** a worker records an upstream rate limit at a subsecond timestamp
- **AND** the persisted `blocked_at` truncates that timestamp to the start of the second
- **AND** the latest usage sample was recorded earlier than the exact rate-limit event but later than the persisted whole-second value
- **WHEN** the worker evaluates the account after its local backoff expires
- **THEN** the account remains `RATE_LIMITED`
- **AND** its reset deadline remains intact

#### Scenario: Truly post-block usage can use early recovery

- **GIVEN** the worker retains the runtime marker for the current upstream rate limit
- **AND** a qualifying usage sample is recorded strictly after that exact marker
- **WHEN** the local backoff has expired
- **THEN** the existing fresh-usage early-recovery path MAY reactivate the account

#### Scenario: Repeated selection preserves the precise marker

- **GIVEN** the first selection pass rejects same-second usage that predates the exact runtime block
- **WHEN** that derived rate-limited state is synchronized and selection runs again
- **THEN** the worker retains its precise runtime block timestamp
- **AND** the second pass also keeps the account `RATE_LIMITED`

#### Scenario: Peer worker retains persisted cooldown behavior

- **GIVEN** a worker did not observe the current upstream rate limit
- **WHEN** it evaluates the rate-limited account before the persisted reset deadline
- **THEN** it keeps the account unavailable under the persisted cooldown contract

### Requirement: Account summaries preserve post-block recovery chronology

When `/api/accounts` derives an active display status from a persisted `RATE_LIMITED` account, it MUST require the same qualifying usage-window evidence used by routing to be recorded strictly after persisted `blocked_at`. Credit fields or capacity rows recorded before or at the block MUST NOT make the account summary active while routing still excludes the account.

#### Scenario: Stale credits do not reactivate the account summary

- **GIVEN** an account is persistently `RATE_LIMITED` with a `blocked_at` marker
- **AND** its usable credit fields and capacity rows were recorded before that marker
- **WHEN** `/api/accounts` builds the account summary after the reset deadline
- **THEN** the summary remains `rate_limited`

#### Scenario: Post-block evidence keeps display and routing aligned

- **GIVEN** a qualifying recovery row is recorded strictly after persisted `blocked_at`
- **WHEN** both routing and account-summary status are evaluated
- **THEN** both surfaces MAY apply the existing recovery rules
