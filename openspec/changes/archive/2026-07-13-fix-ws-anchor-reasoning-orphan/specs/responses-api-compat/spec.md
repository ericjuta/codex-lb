## ADDED Requirements

### Requirement: Proxy-injected continuity anchors preserve reasoning pairing
When the service rewrites a client's self-contained websocket full replay into a proxy-injected `previous_response_id` plus a sliced input delta, it MUST verify that the sliced delta is reasoning-consistent before using it. A delta is reasoning-consistent unless it contains an assistant `message` item that is not preceded by a `reasoning` item within the same delta; re-sent `reasoning` items without a following message and complete `reasoning`-then-`message` groups are consistent because upstream accepts and dedupes them on anchored turns. If the delta would not be reasoning-consistent, the service MUST skip anchor injection for that request and forward the client's original full replay unchanged, and it MUST log a distinct skip reason for observability.


#### Scenario: slice boundary would orphan an assistant message from its reasoning item
- **WHEN** a websocket `/backend-api/codex/responses` request has no `previous_response_id` and its input prefix matches the stored continuity fingerprint
- **AND** the sliced delta `input[stored_count:]` begins with or contains an assistant `message` item whose paired `reasoning` item lies before the slice boundary
- **THEN** the service does not inject `previous_response_id`
- **AND** the request is forwarded upstream with the client's original full input
- **AND** the service logs an anchor-injection skip with a reasoning-orphan reason

#### Scenario: reasoning-consistent delta still uses the anchor
- **WHEN** a websocket `/backend-api/codex/responses` request has no `previous_response_id` and its input prefix matches the stored continuity fingerprint
- **AND** the sliced delta contains only self-consistent items (for example tool outputs whose calls are anchored upstream, or complete reasoning+message groups)
- **THEN** the service injects `previous_response_id` and forwards the sliced delta as today

#### Scenario: reasoning-led incremental delta keeps the anchor
- **WHEN** a websocket `/backend-api/codex/responses` request has no `previous_response_id` and its input prefix matches the stored continuity fingerprint
- **AND** the sliced delta begins with the prior turn's outputs (`reasoning` items, tool calls, and their outputs) followed by new user input, with any assistant `message` preceded by a `reasoning` item within the delta
- **THEN** the service injects `previous_response_id` and forwards the sliced delta

### Requirement: Orphaned-reasoning rejections of proxy-injected anchors recover via full replay
When upstream rejects a websocket turn with an `invalid_request_error` stating that an item was provided without its required `reasoning` item, and the service injected the `previous_response_id` for that turn while retaining a retry-safe self-contained full replay body, the service MUST treat the failure like a stale-anchor continuity loss: reconnect and replay the retained full payload as a fresh turn without `previous_response_id` instead of forwarding the raw upstream error. If no retry-safe full replay body was retained, the service MUST surface a retryable continuity failure rather than the raw upstream invalid-request error. Client-authored payloads whose anchors were not proxy-injected MUST NOT trigger this recovery and continue to receive the upstream error unchanged.


#### Scenario: proxy-injected anchor turn hits the orphaned-reasoning 400
- **WHEN** the service injected `previous_response_id` into a websocket turn and retained a retry-safe full replay body
- **AND** upstream emits `invalid_request_error` with a message matching "was provided without its required 'reasoning' item" before `response.created`
- **THEN** the service reconnects the upstream websocket
- **AND** it replays the retained full payload without `previous_response_id`
- **AND** the downstream client receives the recovered response events, not the raw invalid-request error
- **AND** the service logs that the orphaned-reasoning recovery replay fired

#### Scenario: orphaned-reasoning 400 without a retained replay body
- **WHEN** the service injected `previous_response_id` into a websocket turn but no retry-safe full replay body was retained
- **AND** upstream emits the orphaned-reasoning `invalid_request_error` before `response.created`
- **THEN** the downstream client receives a retryable continuity failure rather than the raw upstream invalid-request error

#### Scenario: client-authored anchor is not rewritten
- **WHEN** a websocket turn carries a client-authored `previous_response_id` that the service did not inject
- **AND** upstream emits the orphaned-reasoning `invalid_request_error`
- **THEN** the service forwards the upstream error to the client unchanged
