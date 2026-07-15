## ADDED Requirements

### Requirement: Upstream rate-limit cooldown honors the Retry-After hint duration

The account cooldown SHALL last for the full duration expressed by a
`try again in` hint on an upstream rate-limit error. The parser SHALL
recognize hour, minute, second, and millisecond units, including word forms,
and SHALL sum compound hints. Unsupported longer words whose prefixes match a
unit MUST NOT be misread as that unit. When no duration is recognized, the
system SHALL use the error-count backoff schedule. A rate-limited account SHALL
NOT be re-selected before its cooldown elapses.

When the 429 carries no explicit reset metadata, the resolved deadline MUST be
persisted in `accounts.reset_at`. Parsed hint deadlines MUST be rounded up to
the next whole second, while fallback backoff deadlines MUST be at least
`RATE_LIMITED_MIN_COOLDOWN_SECONDS` (30 seconds) in the future. Explicit
upstream reset metadata MUST continue to be persisted as supplied.

#### Scenario: Compound hint sets the full cooldown

- **GIVEN** an upstream 429 whose message says `try again in 6m0s`
- **WHEN** the balancer records the rate limit
- **THEN** the account is not re-selected for 360 seconds

#### Scenario: Unparseable hint uses bounded fallback

- **GIVEN** an upstream 429 without reset metadata or a recognizable duration
- **WHEN** the balancer records the rate limit
- **THEN** the persisted row is `RATE_LIMITED` with `blocked_at` set
- **AND** `reset_at` is at least 30 seconds in the future

#### Scenario: Fractional hint remains in the future after persistence

- **GIVEN** an upstream 429 whose message says `try again in 500ms`
- **WHEN** the integer reset deadline is persisted
- **THEN** the persisted deadline is strictly in the future

### Requirement: Rate-limit cooldowns are enforced across processes

A process that did not observe the current upstream 429 MUST NOT transition a
`RATE_LIMITED` account to `ACTIVE` while its persisted reset deadline is in
the future. A row with `blocked_at` set and no `reset_at` MUST remain
rate-limited until at least `blocked_at + 30 seconds`. Recovery writes MUST
use the existing compare-and-set status path.

This constraint applies to selection and background usage-refresh recovery.
Only a process whose runtime block marker is at least as recent as the
persisted `blocked_at` MAY use the existing fresh-usage early-recovery path.
Rows marked rate-limited from stale window data without `blocked_at` retain
their existing recovery behavior.

#### Scenario: Peer process preserves a running cooldown

- **GIVEN** worker A persists a 429 cooldown for an account
- **AND** worker B observes usage below the quota limit before that deadline
- **WHEN** worker B evaluates or refreshes the account
- **THEN** the account remains `RATE_LIMITED`
- **AND** its `reset_at` and `blocked_at` remain intact

#### Scenario: Legacy row receives a minimum floor

- **GIVEN** a `RATE_LIMITED` row with `blocked_at` five seconds ago and no `reset_at`
- **WHEN** a fresh worker evaluates the account
- **THEN** the account remains unavailable until the 30-second floor elapses

#### Scenario: Stale runtime state cannot unlock a newer peer block

- **GIVEN** a worker retains expired runtime state from an earlier 429
- **AND** a peer has persisted a newer `blocked_at` and future `reset_at`
- **WHEN** the first worker evaluates the account
- **THEN** the newer persisted cooldown remains authoritative

### Requirement: Transient balancer health signals are process-local

Transient error counts, error-backoff windows, drain and probe tiers MUST
remain process-local advisory state, as MUST probe success streaks and
in-flight pressure. Persisted status, `reset_at`, and `blocked_at` MUST be
the shared cross-process health signals.

#### Scenario: Workers converge independently on transient failures

- **GIVEN** worker A locally drains an account after transient failures
- **WHEN** worker B has not observed those failures
- **THEN** worker B MAY continue routing to that account
- **AND** worker B applies its own transient backoff after its own observations
