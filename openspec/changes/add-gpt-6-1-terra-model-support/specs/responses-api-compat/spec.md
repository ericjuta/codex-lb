## ADDED Requirements

### Requirement: GPT-6.1 Terra Cursor aliases preserve existing normalization precedence

The existing known Cursor reasoning and speed suffix normalization MUST support `gpt-6.1-terra`. A recognized reasoning suffix MUST override explicit reasoning effort, as for existing supported models. An explicit service tier MUST retain precedence over a speed suffix. Without a reasoning suffix, explicit reasoning MUST remain unchanged. Unknown suffix tokens MUST leave the requested model unchanged.

#### Scenario: Terra reasoning and speed labels normalize
- **WHEN** a request names `gpt-6.1-terra-high-fast` without explicit reasoning or service-tier fields
- **THEN** the forwarded model is `gpt-6.1-terra`, reasoning effort is `high`, and service tier is `priority`

#### Scenario: Existing reasoning and service-tier precedence is retained
- **WHEN** a request names `gpt-6.1-terra-high-fast` with explicit effort `low` and tier `flex`
- **THEN** the model normalizes to `gpt-6.1-terra`, effort becomes `high`, and tier remains `flex`

#### Scenario: Unknown suffix remains literal
- **WHEN** a request names `gpt-6.1-terra-unknown`
- **THEN** the requested model remains unchanged
