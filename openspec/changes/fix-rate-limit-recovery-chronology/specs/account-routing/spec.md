## ADDED Requirements

### Requirement: Local rate-limit recovery preserves exact event chronology

When the process that observed the current upstream rate limit evaluates fresh-usage early recovery, it MUST compare usage evidence with that process's precise runtime block timestamp. Usage recorded before or at the exact runtime block timestamp MUST NOT reactivate the account, even when the usage timestamp is newer than the whole-second persisted `blocked_at` value. Usage recorded strictly after the exact runtime block timestamp MAY use the existing early-recovery path.

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

#### Scenario: Peer worker retains persisted cooldown behavior

- **GIVEN** a worker did not observe the current upstream rate limit
- **WHEN** it evaluates the rate-limited account before the persisted reset deadline
- **THEN** it keeps the account unavailable under the persisted cooldown contract
