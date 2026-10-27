# account-routing Specification

## Purpose
Describe relative-availability account routing, operator tuning, diagnostic privacy, and rate-limit recovery chronology.
## Requirements
### Requirement: Relative availability routing
The selector SHALL support `relative_availability` routing only after existing eligibility, health-tier, model-plan, quota, cooldown, circuit-breaker, and budget-safety gates. It SHALL compute raw scores as remaining secondary-window credits / seconds until that window resets, with bounded fallbacks for unknown or near-immediate resets. It SHALL select from the highest weighted candidates using configured power and top-K.

#### Scenario: Soon-resetting usable credits are preferred
- **GIVEN** two healthy eligible accounts with equal remaining secondary credits
- **AND** one account's secondary window resets sooner
- **WHEN** account selection uses `relative_availability`
- **THEN** the sooner-resetting account receives the higher relative-availability score

#### Scenario: Relative availability preserves canonical gates
- **GIVEN** one account is paused, deactivated, rate-limited, quota-exceeded, cooling down, or outside the requested model plan
- **WHEN** account selection uses `relative_availability`
- **THEN** that account is not selected by the relative-availability strategy

### Requirement: Relative availability dashboard tuning
Dashboard settings SHALL expose `relative_availability_power` and `relative_availability_top_k` alongside the routing strategy. The backend SHALL require positive power and integer top-K from 1 through 20. The dashboard UI SHALL reject non-integer top-K without truncation.

#### Scenario: Sticky fallback uses configured tuning
- **GIVEN** a sticky request has no usable pinned account
- **AND** relative-availability routing is enabled with non-default power or top-K settings
- **WHEN** the load balancer falls back to fresh selection
- **THEN** it applies the configured relative-availability power and top-K values

#### Scenario: Decimal top-K input is rejected
- **WHEN** an operator enters `1.5` for relative availability top-K
- **THEN** the dashboard does not enable saving that value as `1`

### Requirement: Relative availability logs avoid raw account emails
Relative-availability selection diagnostics SHALL identify accounts using stable internal account IDs or another non-PII identifier. They SHALL NOT emit raw account emails in candidate, top-K, winner, or hot-path selected-account logs.

#### Scenario: Candidate logs use account IDs
- **WHEN** relative-availability routing logs candidate or winner diagnostics
- **THEN** the log message includes the candidate account ID
- **AND** the log message does not include the account email address

### Requirement: Local rate-limit recovery preserves exact event chronology

For fresh-usage early recovery, the current upstream rate-limit observer MUST compare usage to its precise runtime block timestamp. Usage at/before it MUST NOT reactivate the account, even if newer than persisted whole-second `blocked_at`. Strictly later usage MAY use existing recovery. While `RATE_LIMITED`, derived-state synchronization MUST preserve that marker over equal/older persisted markers across selections. Processes lacking a matching current marker MUST enforce persisted cooldown.

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

To display a persisted `RATE_LIMITED` account as active, `/api/accounts` MUST require routing's qualifying usage-window evidence recorded strictly after persisted `blocked_at`. Credit fields or capacity rows recorded at or before the block MUST NOT activate the summary while routing excludes the account.

#### Scenario: Stale credits do not reactivate the account summary

- **GIVEN** an account is persistently `RATE_LIMITED` with a `blocked_at` marker
- **AND** its usable credit fields and capacity rows were recorded before that marker
- **WHEN** `/api/accounts` builds the account summary after the reset deadline
- **THEN** the summary remains `rate_limited`

#### Scenario: Post-block evidence keeps display and routing aligned

- **GIVEN** a qualifying recovery row is recorded strictly after persisted `blocked_at`
- **WHEN** both routing and account-summary status are evaluated
- **THEN** both surfaces MAY apply the existing recovery rules

