## ADDED Requirements

### Requirement: GPT-6.2 Cursor aliases use existing suffix normalization

The existing Cursor reasoning and speed suffix normalization MUST support `gpt-6.2-sol` and `gpt-6.2-astra` with unchanged precedence rules.

#### Scenario: GPT-6.2 reasoning and speed labels normalize
- **WHEN** a request names `gpt-6.2-sol-extra-high-fast` without explicit reasoning or service-tier fields
- **THEN** the forwarded model is `gpt-6.2-sol`, reasoning effort is `high`, and service tier is `priority`
