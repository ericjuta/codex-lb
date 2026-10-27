## ADDED Requirements

### Requirement: GPT-6.1 Terra is discoverable before registry refresh

Before successful upstream refresh, both model catalogs MUST include `gpt-6.1-terra` with the native metadata and plan availability specified below. Other models' metadata MUST remain unchanged. A successful upstream refresh MUST remain authoritative.

#### Scenario: Offline Codex discovery
- **GIVEN** no refreshed registry snapshot
- **WHEN** a client fetches `/backend-api/codex/models`
- **THEN** Terra reports display name `GPT-6.1 Terra`, input context `500000`, maximum context `872000`, minimum client `0.153.0`, default reasoning `low`, and WebSocket preference
- **AND** reasoning levels are `low`, `medium`, `high`, `xhigh`, `max`, and `ultra`
- **AND** its default service tier is null and Fast tier description is `1.5x speed`
- **AND** reasoning-effort updates are supported and multi-agent reasoning effort is `xhigh`

#### Scenario: Newly advertised plans can select Terra
- **GIVEN** no refreshed registry snapshot
- **WHEN** model availability is evaluated for Terra on `hc`, `hc_consumption`, `law`, or `rosalind_academic`
- **THEN** the plan is eligible for Terra
- **AND** Terra's plan set is exactly the existing GPT-6 bootstrap plan set plus `hc_consumption`, `law`, and `rosalind_academic`

### Requirement: GPT-6.1 Terra exposes separate input and output budgets

The OpenAI-compatible catalog MUST report a known fallback output budget of `128000` for Terra, separately from its `500000` backend input budget. Valid upstream output metadata and explicit operator context overrides MUST retain their existing precedence.

#### Scenario: OpenAI-compatible Terra discovery
- **GIVEN** no refreshed registry snapshot or operator context override
- **WHEN** a client fetches `/v1/models`
- **THEN** Terra reports `500000` input/context tokens and `128000` maximum output tokens in compatibility projections
- **AND** the output budget is not added to the input budget
