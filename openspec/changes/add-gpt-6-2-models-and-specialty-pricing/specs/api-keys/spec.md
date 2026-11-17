## ADDED Requirements

### Requirement: GPT-6.2 costs use model-specific published pricing

The system MUST resolve `gpt-6.2-astra*` and `gpt-6.2-sol*` to the rates below. Long-context rates MUST apply to the full request only when input exceeds `272000` tokens. Flex requests MUST price at Standard because no Flex rate is published.

#### Scenario: GPT-6.2 costs follow the published rate card
- **WHEN** accounting prices a GPT-6.2 request
- **THEN** it uses these USD rates per million tokens:

| Model | Tier | Input | Cached input | Output | Long input | Long cached input | Long output |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt-6.2-astra | Standard | 8 | 0.40 | 40 | 16 | 0.80 | 60 |
| gpt-6.2-astra | Priority/Fast | 16 | 0.80 | 80 | 32 | 1.60 | 120 |
| gpt-6.2-astra | Batch | 4 | 0.20 | 20 | 8 | 0.40 | 30 |
| gpt-6.2-sol | Standard | 2 | 0.10 | 10 | 4 | 0.20 | 15 |
| gpt-6.2-sol | Priority/Fast | 4 | 0.20 | 20 | 8 | 0.40 | 30 |
| gpt-6.2-sol | Batch | 1 | 0.05 | 5 | 2 | 0.10 | 7.5 |

### Requirement: Ultrafast requests use a per-model multiplier

When a model defines an Ultrafast multiplier, `ultrafast` requests MUST be priced at that multiple of the Standard rates for the request's context length. Models without a multiplier MUST keep Priority/Fast rates for `ultrafast`.

#### Scenario: GPT-6.2 Ultrafast is three times Standard
- **WHEN** a `gpt-6.2-astra` request uses the `ultrafast` tier
- **THEN** short-context rates are `24` input, `1.20` cached input and `120` output

#### Scenario: GPT-6.1 Sol Ultrafast is six times Standard
- **WHEN** a `gpt-6.1-sol` request uses the `ultrafast` tier
- **THEN** short-context rates are `12` input, `0.60` cached input and `60` output

#### Scenario: Models without a multiplier are unchanged
- **WHEN** a `gpt-6.1-terra` request uses the `ultrafast` tier
- **THEN** it is priced at Terra's Priority/Fast rates

### Requirement: Specialty and GPT-6.1 Sol models have explicit price rows

The system MUST price the models below at their own rates rather than another family's alias. Where a long-context column is listed, it MUST apply above `272000` input tokens.

#### Scenario: Specialty rate card
- **WHEN** accounting prices one of these models at the Standard tier
- **THEN** it uses these USD rates per million tokens:

| Model | Input | Cached input | Output | Long input | Long cached input | Long output |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt-6.1-sol | 2 | 0.10 | 10 | 4 | 0.20 | 15 |
| gpt-6-astra-law | 10 | 1 | 50 | - | - | - |
| gpt-6-cyber | 20 | 2 | 100 | 40 | 4 | 150 |
| gpt-6-rosalind | 15 | 1.5 | 75 | 30 | 3 | 112.5 |
| gpt-5.6-cyber | 12.5 | 1.25 | 75 | 25 | 2.5 | 112.5 |
| gpt-5.5-cyber | 12.5 | 1.25 | 75 | - | - | - |
| gpt-rosalind-discovery | 5 | 0.5 | 25 | - | - | - |
| gpt-rosalind-research | 5 | 0.5 | 25 | - | - | - |

#### Scenario: Cyber preview alias does not fall back to GPT-5.5
- **WHEN** cost accounting sees `gpt-5.5-cyber-preview`
- **THEN** it uses `gpt-5.5-cyber` pricing
