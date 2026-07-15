# live-usage-ingestion Specification

## Purpose
TBD - created by archiving change fix-rate-limit-recovery-chronology. Update Purpose after archive.
## Requirements
### Requirement: Direct Responses WebSockets publish passive usage snapshots

The direct `/v1/responses` and `/backend-api/codex/responses` WebSocket relay MUST inspect upstream text frames for `codex.rate_limits` events and publish parsed snapshots through the existing live-usage hub, attributed to the account serving the upstream connection. This tap MUST preserve the fire-and-forget serving-path contract and MUST apply to both public Responses WebSocket route variants.

#### Scenario: Direct WebSocket frame updates live usage

- **WHEN** either direct Responses WebSocket route receives an upstream `codex.rate_limits` text frame
- **THEN** the relay publishes one parsed snapshot for the serving account
- **AND** normal downstream frame processing continues

#### Scenario: Unrelated WebSocket frames are not published

- **WHEN** a direct Responses WebSocket receives an upstream text frame without the rate-limit event marker
- **THEN** the relay does not publish a live usage snapshot for that frame
