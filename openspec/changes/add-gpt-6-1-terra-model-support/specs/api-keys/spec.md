## ADDED Requirements

### Requirement: GPT-6.1 Terra costs use model-specific published pricing

The system MUST resolve `gpt-6.1-terra` and aliases matching `gpt-6.1-terra*` to the rates below. Long-context rates MUST apply to the full request only when input exceeds `272000` tokens. Cached input MUST NOT also be charged at uncached rates.

#### Scenario: Terra costs follow the published rate card
- **WHEN** accounting prices a Terra request
- **THEN** it uses these USD rates per million tokens for the applicable tier and context length:

| Tier | Input | Cached input | Output | Long input | Long cached input | Long output |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Standard | 1 | 0.05 | 5 | 2 | 0.10 | 7.5 |
| Priority/Fast | 2 | 0.10 | 10 | 4 | 0.20 | 15 |
| Flex/Batch | 0.5 | 0.025 | 2.5 | 1 | 0.05 | 3.75 |

#### Scenario: Terra uses its five-percent cache rate
- **WHEN** a standard Terra request consumes 200000 input tokens including 100000 cached tokens and 10000 output tokens
- **THEN** its computed cost is USD `0.155`

#### Scenario: Threshold equality remains short context
- **WHEN** a Terra request has exactly 272000 input tokens
- **THEN** short-context rates apply for its service tier

#### Scenario: Longer requests use long-context tier rates
- **WHEN** a Terra request has more than 272000 input tokens
- **THEN** the entire request uses the long-context column for its service tier

#### Scenario: Dated Terra aliases retain Terra pricing
- **WHEN** cost accounting sees `gpt-6.1-terra-2026-10-27`
- **THEN** it uses Terra pricing rather than another GPT family
