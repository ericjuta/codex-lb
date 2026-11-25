## ADDED Requirements

### Requirement: Transient account health is scoped to the served model

When the proxy records a transient upstream error or a connect-phase `403` cooldown for an account that was serving a known model, that state MUST count only against selecting the account for the same model. It MUST NOT exclude, back off or deprioritize the account for another model. Rate-limit, quota and permanent failures MUST stay account-wide. A failure recorded without a model MUST stay account-wide.

#### Scenario: A throttled model does not bench the account for another model

- **GIVEN** an account recorded three consecutive transient errors while serving model A
- **WHEN** a request for model B runs account selection
- **THEN** the account is eligible for model B
- **AND** a request for model A finds the account in error backoff

#### Scenario: A key pinned to one account keeps its other models

- **GIVEN** an API key scoped to a single account
- **AND** that account is in error backoff for model A
- **WHEN** the key requests model B
- **THEN** selection returns the account instead of "No available accounts"

#### Scenario: A success clears only its own model

- **GIVEN** an account holds transient errors for model A
- **WHEN** a request for model B succeeds on the account
- **THEN** the errors recorded for model A remain
- **AND** a later success for model A clears them

#### Scenario: A failure without a model stays account-wide

- **WHEN** the proxy records three consecutive transient errors for an account without naming a model
- **THEN** the account is in error backoff for every model

#### Scenario: A rate limit stays account-wide

- **WHEN** upstream answers a request for model A with `rate_limit_exceeded`
- **THEN** the account is rate limited for every model

### Requirement: Model-scoped transient health keeps the account-wide thresholds

Model-scoped transient health MUST follow the account-wide rules, per model: three consecutive errors start a 30-second backoff that doubles per further error up to 300 seconds; the backoff fallback picks the account nearest recovery; an elapsed backoff or cooldown clears the count. With soft drain enabled, the drain error threshold MUST deprioritize the account for that model only. The stored health tier MUST stay account-wide.

#### Scenario: Elapsed backoff returns the model with a clean count

- **GIVEN** an account is in error backoff for model A
- **WHEN** the backoff period has elapsed and a request for model A runs selection
- **THEN** the account is eligible
- **AND** one further transient error for model A does not restart the backoff

#### Scenario: Backoff fallback still serves a model whose accounts are all backed off

- **GIVEN** every account that serves model A is in error backoff for model A
- **AND** more than one such account exists
- **WHEN** a request for model A runs selection with the backoff fallback allowed
- **THEN** selection returns the account whose backoff ends first

#### Scenario: Model errors do not change the stored health tier

- **GIVEN** soft drain is enabled and an account's stored health tier is healthy
- **WHEN** the account records two transient errors for model A within the drain error window
- **THEN** selection for model A treats the account as draining
- **AND** selection for model B treats the account as healthy
