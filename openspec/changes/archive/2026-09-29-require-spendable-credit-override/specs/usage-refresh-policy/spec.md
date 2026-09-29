## MODIFIED Requirements

### Requirement: Credit-backed secondary quota remains usable

When account status is derived from persisted usage snapshots, an exhausted secondary-window usage percentage MUST NOT by itself mark an account `quota_exceeded` if the governing usage snapshot reports usable credit-backed capacity. Usable credit-backed capacity is present only when `credits_unlimited` is true or `credits_balance` is positive. A `credits_has` value of true with `credits_balance` missing, zero, or negative MUST NOT by itself establish usable credit-backed capacity.

This credit-aware interpretation MUST be shared by proxy account selection and account/dashboard summary status mapping so an account selected as usable by the proxy is not simultaneously displayed as `quota_exceeded` in the operator summary. Exhausted primary-window usage MUST still take precedence as `rate_limited`, and paused or deactivated accounts MUST NOT be reactivated solely because a usage snapshot reports usable credits.

#### Scenario: Secondary quota exhausted with credits remains active

- **GIVEN** an account is persisted as `quota_exceeded`
- **AND** its governing secondary-window usage reports `used_percent >= 100`
- **AND** the same usage snapshot reports usable credit-backed capacity
- **WHEN** proxy selection or account-summary mapping derives the effective status
- **THEN** the effective status is `active`

#### Scenario: Bare has-credits flag without spendable balance does not override secondary exhaustion

- **GIVEN** an account's governing secondary-window usage reports `used_percent >= 100`
- **AND** its primary-window usage reports `used_percent < 100`
- **AND** the same usage snapshot reports `credits_has = true`, `credits_unlimited` not true, and `credits_balance` missing, zero, or negative
- **WHEN** account-summary mapping derives the effective status with status inference from usage enabled
- **OR** proxy selection derives the effective status for an account persisted as `quota_exceeded` whose runtime reset deadline is still in the future
- **THEN** the effective status is `quota_exceeded`

#### Scenario: Exhausted primary window keeps rate-limit precedence

- **GIVEN** an account has usable credit-backed capacity in its usage snapshot
- **AND** its primary-window usage reports `used_percent >= 100`
- **WHEN** proxy selection or account-summary mapping derives the effective status
- **THEN** the effective status is `rate_limited`

#### Scenario: Operator-disabled states are preserved

- **GIVEN** an account is `paused` or `deactivated`
- **AND** its usage snapshot reports usable credit-backed capacity
- **WHEN** proxy selection or account-summary mapping derives the effective status
- **THEN** the account remains `paused` or `deactivated`
