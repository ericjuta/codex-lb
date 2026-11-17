## ADDED Requirements

### Requirement: GPT-6.2 models are discoverable before registry refresh

Before successful upstream refresh, both model catalogs MUST include `gpt-6.2-sol` and `gpt-6.2-astra` with the metadata in the scenarios below. A successful upstream refresh MUST remain authoritative. The fallback Codex client version MUST be at least `0.166.0`.

#### Scenario: Offline Codex discovery of GPT-6.2 Sol
- **GIVEN** no refreshed registry snapshot
- **WHEN** a client fetches `/backend-api/codex/models`
- **THEN** `gpt-6.2-sol` reports input context `500000`, maximum context `872000`, minimum client `0.166.0`, default reasoning `low`, priority `1`, and text, image and audio input
- **AND** its service tiers are `priority` and `ultrafast`

#### Scenario: Offline Codex discovery of GPT-6.2 Astra
- **GIVEN** no refreshed registry snapshot
- **WHEN** a client fetches `/backend-api/codex/models`
- **THEN** `gpt-6.2-astra` reports input context `272000`, maximum context `872000`, minimum client `0.166.0`, default reasoning `low`, priority `2`, and text and image input
- **AND** its only service tier is `priority`

#### Scenario: GPT-6.2 plan availability
- **GIVEN** no refreshed registry snapshot
- **WHEN** plan availability is evaluated for either GPT-6.2 model
- **THEN** `hc_consumption`, `law` and `rosalind_academic` are eligible
- **AND** `free`, `free_workspace` and `k12` are not

#### Scenario: OpenAI-compatible output budget
- **GIVEN** no refreshed registry snapshot or operator context override
- **WHEN** a client fetches `/v1/models`
- **THEN** both GPT-6.2 models report `128000` maximum output tokens, separate from their input budget
