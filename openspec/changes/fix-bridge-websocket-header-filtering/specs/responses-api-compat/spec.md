## ADDED Requirements

### Requirement: Upstream websocket handshakes exclude HTTP content-negotiation headers

The service MUST exclude the HTTP content-negotiation headers `accept` and
`content-type`, hop-by-hop headers, and websocket handshake control headers
(`sec-websocket-*`, `accept-encoding`, `cookie`) whenever it builds upstream
websocket handshake headers from inbound HTTP request headers, including HTTP
responses bridge session creation and bridge session reconnection. Internal
websocket protocol headers set by the service itself (such as the responses
websocket beta header) are not affected.

#### Scenario: bridge session creation filters content-negotiation headers

- **WHEN** the HTTP responses bridge opens an upstream websocket session for a
  downstream request carrying `accept: text/event-stream` and
  `content-type: application/json`
- **THEN** the upstream websocket handshake headers exclude `accept` and
  `content-type`
- **AND** non-excluded end-to-end headers are still forwarded

#### Scenario: bridge session reconnection filters content-negotiation headers

- **WHEN** the HTTP responses bridge reconnects an upstream websocket session
  using stored inbound headers that include `accept` and `content-type`
- **THEN** the rebuilt upstream websocket handshake headers exclude `accept`
  and `content-type`
