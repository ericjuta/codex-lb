## ADDED Requirements

### Requirement: WebSocket Responses Stream Continuation Folding
codex-lb SHALL apply CodexCont continuation folding to continuation-eligible
Responses streams served over the downstream WebSocket transport
(`/backend-api/codex/responses`) when
`CODEX_LB_CODEX_CONTINUATION_WEBSOCKET_ENABLED=true` and the continuation gates
pass (continuation enabled, streaming, reasoning not explicitly disabled). When
the flag is false, the WebSocket transport MUST relay upstream events unchanged.

#### Scenario: Truncated WebSocket round continues
- **WHEN** a downstream WebSocket Responses turn is continuation eligible and its
  upstream terminal event reports `usage.output_tokens_details.reasoning_tokens`
  matching `truncation_step * n - 2` with encrypted reasoning available
- **AND** configured continuation caps allow another round
- **THEN** codex-lb does not emit the truncated round's tentative final output to
  the downstream client
- **AND** codex-lb opens a continuation round that appends the prior encrypted
  reasoning plus the configured continuation marker to the next upstream request
- **AND** the downstream client receives the folded rounds as one coherent
  response stream

#### Scenario: WebSocket continuation disabled
- **WHEN** `CODEX_LB_CODEX_CONTINUATION_WEBSOCKET_ENABLED=false`
- **THEN** the downstream WebSocket transport relays upstream events without
  opening hidden continuation rounds

### Requirement: WebSocket Hidden Rounds Reuse Selected Upstream
Hidden WebSocket continuation rounds MUST reuse the already-selected upstream
account, authorization headers, upstream route, and Codex client/session of the
visible round. They MUST NOT re-enter account selection as separate
user-visible requests and MUST NOT create independent API-key usage
reservations.

#### Scenario: Hidden WebSocket round stays on the selected account
- **WHEN** a WebSocket continuation round is opened for a truncated turn
- **THEN** the round is sent to the same upstream account and route as the
  visible round
- **AND** no additional account selection or API-key reservation is created for
  the hidden round

### Requirement: WebSocket Settlement Uses Proxy Billed Usage
codex-lb WebSocket settlement MUST use `metadata.proxy_billed_usage` (the true
aggregated usage across folded rounds) for API-key usage settlement and
request-log usage whenever a WebSocket Responses terminal event carries it,
rather than the agent-facing `response.usage`. Downstream clients MUST still
receive the agent-facing `response.usage`. When no `metadata.proxy_billed_usage`
is present, settlement MUST use `response.usage` as before.

#### Scenario: Folded WebSocket stream settles aggregated usage
- **WHEN** a folded WebSocket stream returns agent-facing `response.usage` and
  `metadata.proxy_billed_usage`
- **THEN** downstream clients receive the agent-facing `response.usage`
- **AND** codex-lb API-key settlement and request logs record
  `metadata.proxy_billed_usage`

#### Scenario: Unfolded WebSocket stream settles response usage
- **WHEN** a WebSocket terminal event has no `metadata.proxy_billed_usage`
- **THEN** codex-lb API-key settlement and request logs record `response.usage`
