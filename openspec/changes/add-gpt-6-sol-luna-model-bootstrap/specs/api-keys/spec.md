## ADDED Requirements

### Requirement: GPT-6 Sol and Luna pricing is recognized

The system MUST recognize `gpt-6-sol` and `gpt-6-luna` when computing request
costs. Suffixed and dated aliases matching `gpt-6-sol*` MUST resolve to the
canonical `gpt-6-sol` pricing entry, and aliases matching `gpt-6-luna*` MUST
resolve to the canonical `gpt-6-luna` pricing entry. These aliases MUST NOT
resolve through `gpt-6-astra`, bare `gpt-6`, or any GPT-5 pricing entry.

Rates are USD per 1M tokens as published on the OpenAI API pricing page on
2026-09-23. Requests above `272000` input tokens MUST apply the long-context
rates for their service tier. Cache-write pricing is not represented until the
pricing schema gains a cache-write field.

For `gpt-6-sol`:
- standard requests MUST use `$2.00` input, `$0.20` cached input, and `$10.00`
  output; long-context standard requests MUST use `$4.00`, `$0.40`, and
  `$15.00`;
- Priority/Fast requests MUST use `$4.00`, `$0.40`, and `$20.00`;
  long-context Priority/Fast requests MUST use `$8.00`, `$0.80`, and `$30.00`;
- Flex/Batch requests MUST use `$1.00`, `$0.10`, and `$5.00`.

For `gpt-6-luna`:
- standard requests MUST use `$0.10` input, `$0.01` cached input, and `$0.50`
  output; long-context standard requests MUST use `$0.20`, `$0.02`, and
  `$0.75`;
- Priority/Fast requests MUST use `$0.20`, `$0.02`, and `$1.00`;
  long-context Priority/Fast requests MUST use `$0.40`, `$0.04`, and `$1.50`;
- Flex/Batch requests MUST use `$0.05`, `$0.005`, and `$0.25`.

#### Scenario: Canonical GPT-6 Sol uses standard pricing

- **WHEN** a standard-tier request completes for `gpt-6-sol`
- **THEN** the system computes cost using `$2.00` input, `$0.20` cached input, and `$10.00` output rates per 1M tokens

#### Scenario: Canonical GPT-6 Luna uses standard pricing

- **WHEN** a standard-tier request completes for `gpt-6-luna`
- **THEN** the system computes cost using `$0.10` input, `$0.01` cached input, and `$0.50` output rates per 1M tokens

#### Scenario: GPT-6 Sol and Luna aliases resolve to their own pricing

- **WHEN** a request completes for a suffixed or dated model ID such as `gpt-6-sol-2026-09-01` or `gpt-6-luna-2026-09-01`
- **THEN** the system resolves it to the canonical `gpt-6-sol` or `gpt-6-luna` pricing entry respectively
- **AND** the system does not use `gpt-6-astra` or any GPT-5 pricing entry

#### Scenario: GPT-6 Sol and Luna service tiers use published tier rates

- **WHEN** a `gpt-6-sol` or `gpt-6-luna` request completes with `service_tier: "priority"`, `"fast"`, `"flex"`, or an observed accounting tier of `"batch"`
- **THEN** the system computes cost using that model's published rates for that service tier

#### Scenario: GPT-6 Sol and Luna long-context requests use published tier rates

- **WHEN** a `gpt-6-sol` or `gpt-6-luna` request completes with more than 272K input tokens
- **THEN** the system computes cost using that model's long-context rates for the request service tier
