## ADDED Requirements

### Requirement: Force Probe upstream request omits unsupported output-token limit

The direct upstream `responses.create` sent by dashboard Force Probe (`POST /api/accounts/{account_id}/probe`) MUST NOT contain a `max_output_tokens` key at any value. The system MUST NOT substitute another output-token cap, retry the probe without the field, or send more than one upstream request per probe.

The probe body MUST still contain the probe model (the request's `model`, else `DEFAULT_PROBE_MODEL`), the fixed one-dot `instructions` and `input`, `stream=true`, and `store=false`. The request MUST still target `{upstream_base_url}/codex/responses` (with `/backend-api` inserted when absent), carry `Authorization: Bearer <decrypted access token>` and `Accept: text/event-stream`, and carry `chatgpt-account-id` unless the stored id is absent or starts with `email_` or `local_`. The request MUST remain bounded by `PROBE_REQUEST_TIMEOUT_SECONDS` total and `PROBE_CONNECT_TIMEOUT_SECONDS` socket connect, and MUST return once response headers arrive without consuming the SSE body. `probe_status_code` MUST remain the upstream HTTP status verbatim, or `0` when the request fails with a client or timeout error, and the post-probe forced usage refresh, before/after snapshot, audit entry, dashboard authentication, and existing `404`/`409` rejections MUST remain unchanged.

#### Scenario: Probe body carries no output-token limit

- **WHEN** an operator POSTs to `/api/accounts/{account_id}/probe` for an `active`, `rate_limited`, or `quota_exceeded` account
- **THEN** exactly one upstream `responses.create` is sent to `{upstream_base_url}/codex/responses`
- **AND** its JSON body has no `max_output_tokens` key (neither `1`, `16`, nor any other value)
- **AND** its JSON body carries the probe model, the one-dot `instructions` and `input`, `stream=true`, and `store=false`

#### Scenario: Upstream that rejects the field accepts the probe

- **GIVEN** an upstream that responds `400` to any `responses.create` body containing `max_output_tokens` and `200` otherwise
- **WHEN** an operator POSTs to `/api/accounts/{account_id}/probe` for a probeable account
- **THEN** the endpoint responds `200`
- **AND** the response body reports `probeStatusCode` `200`

#### Scenario: Upstream status still propagates verbatim

- **WHEN** the upstream answers the probe with any HTTP status, including a non-2xx status
- **THEN** `probe_status_code` equals that status
- **AND** no second upstream request is sent

#### Scenario: Network failure keeps the zero sentinel within timeout bounds

- **WHEN** the probe request raises a client error or exceeds `PROBE_REQUEST_TIMEOUT_SECONDS` total or `PROBE_CONNECT_TIMEOUT_SECONDS` socket connect
- **THEN** `probe_status_code` is `0`
- **AND** the decrypted access token is not logged

#### Scenario: Account headers and stream handling are preserved

- **WHEN** the probe is sent for an account whose stored `chatgpt_account_id` does not start with `email_` or `local_`
- **THEN** the request carries `Authorization: Bearer <decrypted access token>`, `Accept: text/event-stream`, and `chatgpt-account-id` set to that id
- **AND** the probe returns the status after response headers without reading the SSE body
