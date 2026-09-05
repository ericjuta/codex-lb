# responses-api-compat Delta

## ADDED Requirements

### Requirement: WebSocket tool-search fresh retries require completed client-owned pairs

The direct WebSocket fresh-retry predicate MUST treat `tool_search_call` / `tool_search_output` items as retry-safe only when they form a completed, ordered, self-contained pair whose declared execution owner is omitted or `client`. A status of `completed`, an omitted status, or a null status MUST be treated as completed-compatible; every other status MUST be rejected as incomplete. The call MUST carry dictionary `arguments`. The output MUST carry a `tools` list or a string `output`, but not both. The predicate MUST reject server-owned execution, an output without its matching preceding call, an incomplete status, or an otherwise malformed pair. This check MUST NOT change HTTP compact or HTTP fresh-resend pair policy, and MUST NOT change the ordinary anchored WebSocket trimming boundary.

#### Scenario: Completed client-owned tool-search pair is retry-safe

- **GIVEN** a direct WebSocket full resend contains a completed `tool_search_call` with dictionary `arguments`
- **AND** a matching completed `tool_search_output` with a string `output` or a `tools` list
- **AND** both items omit `execution` or declare `execution: "client"`
- **WHEN** the proxy evaluates the payload for an anchor-free retry
- **THEN** the tool-search pair is accepted as self-contained replay state

#### Scenario: Server-owned tool-search output is not retry-safe

- **GIVEN** a direct WebSocket full resend contains a completed client-owned `tool_search_call`
- **AND** its matching `tool_search_output` declares `execution: "server"`
- **WHEN** the proxy evaluates the payload for an anchor-free retry
- **THEN** the request is not retained as a fresh retry

#### Scenario: Orphan or incomplete tool-search items are not retry-safe

- **GIVEN** a direct WebSocket full resend contains a `tool_search_output` without its matching preceding call, or a tool-search item whose status is neither `completed`, omitted, nor null
- **WHEN** the proxy evaluates the payload for an anchor-free retry
- **THEN** the request is not retained as a fresh retry

#### Scenario: Reused tool-search call IDs are not retry-safe

- **GIVEN** a direct WebSocket full resend reuses a tool-search `call_id` for a second call or a second output
- **WHEN** the proxy evaluates the payload for an anchor-free retry
- **THEN** the request is not retained as a fresh retry

### Requirement: WebSocket fresh retries omit response-owned tool-search IDs

When the proxy retains a self-contained direct WebSocket `response.create` payload for a fresh retry without `previous_response_id`, it MUST remove the top-level `id` field from every `tool_search_call` and `tool_search_output` input item in that retained retry payload. It MUST preserve each paired item’s type, `call_id`, arguments or output, status, relative order, and all other input history. This requirement applies whether the original anchor was supplied by the client or injected from WebSocket continuity state. Preparing the retry MUST NOT mutate caller-owned input and MUST NOT change the ordinary anchored submission.

#### Scenario: Client-supplied anchor retains a sanitized full-history retry

- **GIVEN** a direct Responses WebSocket request supplies `previous_response_id` and self-contained full history containing a paired `tool_search_call` and `tool_search_output` with response-owned IDs
- **WHEN** the proxy prepares both the ordinary anchored submission and its retained anchor-free retry
- **THEN** the ordinary anchored submission follows the existing trimming and forwarding behavior
- **AND** the retained retry preserves the complete original history and paired tool-search content without either tool-search `id`
- **AND** the inbound request remains unchanged

#### Scenario: Proxy-injected anchor retains a sanitized full-history retry

- **GIVEN** WebSocket continuity state lets the proxy replace a matching historical prefix with an injected `previous_response_id`
- **AND** that historical prefix contains a paired `tool_search_call` and `tool_search_output` with response-owned IDs
- **WHEN** the proxy retains the original payload for an anchor-free retry
- **THEN** the anchored submission still contains only the existing incremental delta
- **AND** the retained retry contains the complete original history and paired tool-search content without either tool-search `id`
- **AND** the inbound request remains unchanged

#### Scenario: Stale-anchor retry sends the sanitized retained body
- **GIVEN** the proxy retained a sanitized direct WebSocket fresh-retry body after a client-supplied or injected `previous_response_id`
- **WHEN** upstream rejects that anchored request with `previous_response_not_found` before `response.created`
- **THEN** the proxy reconnects and sends the retained sanitized body without `previous_response_id`
- **AND** the sent `tool_search_call` and `tool_search_output` items still have no top-level `id`

#### Scenario: Unrelated input identity is preserved

- **GIVEN** a retained fresh-retry payload contains non-tool-search items or tool-search fields other than the top-level `id`
- **WHEN** the retry payload is sanitized
- **THEN** those items and fields remain unchanged
