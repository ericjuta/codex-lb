## ADDED Requirements

### Requirement: Internal Responses Lite header is forwarded upstream

The service MUST preserve an inbound `X-OpenAI-Internal-Codex-Responses-Lite` header when calling upstream Responses, compact, or WebSocket transports. The service MUST preserve the header value and MUST NOT disable Responses Lite behavior by removing the header.

#### Scenario: HTTP and compact upstream headers preserve Lite

- **WHEN** a client sends a Responses or compact request with `X-OpenAI-Internal-Codex-Responses-Lite: 1`
- **THEN** the upstream HTTP request headers include `X-OpenAI-Internal-Codex-Responses-Lite: 1`
- **AND** existing authentication, proxy identity, and hop-by-hop header filtering remains in effect

#### Scenario: WebSocket upstream headers preserve Lite

- **WHEN** a client opens a Responses WebSocket with `X-OpenAI-Internal-Codex-Responses-Lite: 1`
- **THEN** the upstream WebSocket connection headers include `X-OpenAI-Internal-Codex-Responses-Lite: 1`
- **AND** existing WebSocket beta and Codex continuity headers are preserved

### Requirement: GPT-5.6 bootstrap metadata advertises Lite Code Mode capabilities

When the static bootstrap catalog is serving `gpt-5.6-sol`, `gpt-5.6-terra`, or `gpt-5.6-luna`, the Codex model metadata MUST include `use_responses_lite=true`, `tool_mode=code_mode_only`, and `experimental_supported_tools=["exec", "wait"]`. The `multi_agent_version` MUST be `v2` for Sol and Terra and `v1` for Luna. A successful live model-catalog refresh MAY replace these fallback entries with upstream metadata.

#### Scenario: Offline GPT-5.6 model discovery preserves tool capabilities

- **GIVEN** the live upstream model catalog has not populated the registry
- **WHEN** a client requests `/backend-api/codex/models`
- **THEN** the GPT-5.6 Sol, Terra, and Luna entries include the Lite and Code Mode capability metadata
- **AND** each entry advertises `exec` and `wait` as experimental supported tools
- **AND** the entries retain their configured multi-agent version
