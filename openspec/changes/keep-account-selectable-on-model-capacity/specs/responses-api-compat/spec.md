## ADDED Requirements

### Requirement: Model-capacity rejections do not exclude the account from the request

When a pre-visible failure is classified `retryable_transient` and its message states that the selected model is at capacity, the proxy MUST still write the account's transient health result but MUST NOT add the account to the request's excluded accounts. A capacity message MUST NOT suppress exclusion for a failure classified `rate_limit` or `quota`, and ordinary transient failures MUST still exclude the account.

#### Scenario: Only account is retried after capacity rejection

- **WHEN** the only eligible account answers HTTP 400 "Selected model is at capacity. Please try a different model." on a stream request
- **THEN** the proxy re-selects the same account and completes when capacity clears.

#### Scenario: Compact request retries the same account

- **WHEN** the same rejection happens on a compact request
- **THEN** the compact walk selects the same account again and succeeds.

#### Scenario: Capacity 500 keeps the walk going but ordinary 500 does not

- **WHEN** every dispatch returns HTTP 500 with the capacity message
- **THEN** the walk continues past the point where an ordinary `server_error` 500 would have exhausted both accounts.
