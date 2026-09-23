## ADDED Requirements

### Requirement: Cursor GPT-6 Sol and Luna model aliases normalize to canonical slugs

For Responses proxy traffic, the service MUST recognize Cursor-style model
aliases formed by appending known suffix tokens (`minimal`, `low`, `medium`,
`high`, `xhigh`, `extra`, `fast`, `priority`, `reasoning`, `thinking`) to the
`gpt-6-sol` and `gpt-6-luna` slugs. The resolver MUST normalize the model to
the matching canonical slug and move recognized reasoning and speed labels into
request fields. Unknown suffix tokens MUST leave the requested model unchanged.
`ultra` and `max` remain unsupported model-name suffix tokens and MUST pass
through unchanged.

#### Scenario: GPT-6 Sol alias normalizes reasoning and service tier

- **WHEN** a client sends a Responses request with `model: "gpt-6-sol-extra-high-fast"`
- **THEN** the forwarded upstream request uses `model: "gpt-6-sol"`
- **AND** the forwarded upstream request uses `reasoning.effort: "high"`
- **AND** the forwarded upstream request uses `service_tier: "priority"`

#### Scenario: GPT-6 Luna alias normalizes reasoning

- **WHEN** a client sends a Responses request with `model: "gpt-6-luna-low"`
- **THEN** the forwarded upstream request uses `model: "gpt-6-luna"`
- **AND** the forwarded upstream request uses `reasoning.effort: "low"`

#### Scenario: GPT-6 Sol ultra-suffixed label is not rewritten

- **WHEN** a client sends a Responses request with `model: "gpt-6-sol-ultra"`
- **THEN** the forwarded upstream request keeps `model: "gpt-6-sol-ultra"`
