## ADDED Requirements

### Requirement: Codex HTTP bridge throughput controls remain independently tunable

The service MUST provide independent settings for Codex HTTP bridge prewarming and the Codex-specific HTTP request budget. The default profile MUST enable Codex bridge prewarming and MUST use a shorter Codex HTTP budget than the general streaming budget so stalled bridge requests fail within a bounded interval.

#### Scenario: Default Codex bridge request uses the bounded HTTP budget

- **WHEN** a Codex-affinity Responses request uses the HTTP bridge transport
- **THEN** its request budget is the Codex-specific HTTP bridge budget
- **AND** WebSocket transport continues to use the general streaming budget

#### Scenario: Prewarm can be disabled independently

- **WHEN** an operator disables Codex HTTP bridge prewarming
- **THEN** request serving remains available without background prewarm activity
