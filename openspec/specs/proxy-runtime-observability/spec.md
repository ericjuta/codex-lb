# proxy-runtime-observability Specification

## Purpose

Define proxy observability contracts so runtime failures, routing decisions, and admission rejections remain diagnosable.
## Requirements
### Requirement: Proxy 4xx/5xx responses are logged with error detail

When the proxy returns a 4xx or 5xx response for a proxied request, the system MUST log the request id, method, path, status code, error code, and error message to the console. For local admission rejections, the log MUST also include the rejection stage or lane.

#### Scenario: Local admission rejection is logged

- **WHEN** the proxy rejects a request locally because a downstream or expensive-work admission lane is full
- **THEN** the console log includes the local response status, normalized error code and message
- **AND** it includes which admission lane or stage rejected the request

### Requirement: Continuity-sensitive responses flows emit explicit operator diagnostics

When the proxy resolves or fails closed a continuity-sensitive follow-up request, the system MUST emit structured diagnostics that let operators determine how continuity ownership was resolved or why the proxy returned a retryable masked error. Fail-closed diagnostics for upstream tool-call linkage corruption MUST label the two upstream variants distinctly: `missing_tool_output` for a call whose output never arrived (upstream message `"No tool output found for function call call_..."`) and `orphaned_tool_output` for a tool output whose call is absent from the resolved previous-response context (upstream message `"No tool call found for function call output with call_id ..."`). The structured fail-closed log MUST include the normalized `upstream_error_code` when the upstream error payload is available, captured before any payload rewriting mutates it. The client-visible error envelope MUST remain `stream_incomplete` (`server_error`) for both variants, and the variant labeling MUST NOT change reconnect-request, grouped-terminal, or rewrite behavior relative to the prior single `missing_tool_output` classification.

#### Scenario: owner resolution source is recorded for a previous-response follow-up

- **WHEN** a websocket, HTTP fallback, or HTTP bridge follow-up request includes `previous_response_id`
- **AND** the proxy resolves the required owner account from a continuity source such as a local bridge session, owner cache, or request-log lookup
- **THEN** the system emits a structured diagnostic describing the continuity surface, source, and outcome
- **AND** the diagnostic does not expose the raw `previous_response_id`

#### Scenario: fail-closed continuity masking is recorded

- **WHEN** the proxy rewrites or returns a retryable continuity error because owner metadata is unavailable, continuity state is lost, or the pinned owner account is unavailable
- **THEN** the system emits a structured diagnostic describing the continuity surface and fail-closed reason
- **AND** Prometheus counters record the low-cardinality source or reason labels for that decision

#### Scenario: orphaned tool-output corruption is labeled distinctly

- **WHEN** a follow-up turn carrying `previous_response_id` receives the upstream error `"No tool call found for function call output with call_id call_X"` (`invalid_request_error`, `param=input`) on the websocket relay, HTTP bridge, or HTTP stream surface
- **THEN** the fail-closed diagnostic and the `codex_lb_continuity_fail_closed_total` counter record reason `orphaned_tool_output` rather than `missing_tool_output`
- **AND** the downstream client still receives the `stream_incomplete` rewrite with the raw upstream message masked
- **AND** the upstream reconnect request is still made where the `missing_tool_output` variant would make it

#### Scenario: websocket_stream fail-closed log includes the upstream error code

- **WHEN** the websocket relay rewrites an in-stream tool-linkage corruption error to the fail-closed `stream_incomplete` terminal
- **THEN** the `continuity_fail_closed` structured log includes the normalized `upstream_error_code` from the upstream error payload

### Requirement: Full upstream conversation archive

The proxy MUST provide an opt-in durable archive of Codex-to-upstream conversation traffic. When enabled, the archive MUST write gzip-compressed newline-delimited JSON records for upstream request payloads, streamed Responses events, compact response payloads, and websocket text or binary frames without performing gzip file I/O in the request event loop during normal operation. The archive writer queue MUST be bounded and MUST apply synchronous write backpressure instead of growing without limit when the background writer is saturated. Archive records MUST include request id, timestamp, direction, traffic kind, transport, account id when known, upstream target metadata, redacted headers, and the full payload or frame body. Credential-bearing headers such as authorization, cookies, proxy authorization, token headers, and API key headers MUST be redacted before persistence. JSON records MUST preserve non-ASCII payload text as UTF-8 rather than Unicode escape sequences. When disabled, no archive file MUST be created by the archive writer.

#### Scenario: operator enables archive for audit

- **WHEN** `CODEX_LB_CONVERSATION_ARCHIVE_ENABLED=true`
- **AND** a Codex Responses request is proxied upstream
- **THEN** the archive records both the outbound upstream payload and inbound upstream events or response body as gzip JSONL
- **AND** credential-bearing headers are stored as redacted values

#### Scenario: archive remains disabled by default

- **WHEN** the archive setting is not enabled
- **THEN** the archive writer does not create conversation archive files

#### Scenario: operator views archived traffic

- **GIVEN** conversation archive files exist as `.jsonl.gz` or legacy `.jsonl`
- **WHEN** an authenticated dashboard operator opens an existing request log detail
- **THEN** the dashboard can find matching archive records by request id across archive files and display payload plus metadata for that request

### Requirement: Optional upstream payload tracing

When request-shape tracing for proxy routing is enabled, the system MUST log affinity decision metadata without exposing full prompt text or full cache keys. The trace MUST include request id, request kind, sticky kind, sticky-key source, whether a session header was present, whether a prompt-cache key was set/injected, and a stable tools hash when tools are present.

#### Scenario: Affinity request-shape tracing is enabled

- **WHEN** the proxy resolves routing for a Responses or compact request while request-shape tracing is enabled
- **THEN** the console shows the chosen sticky kind, sticky-key source, prompt-cache-key presence/injection state, and tools hash
- **AND** the console does not log raw prompt text or the full prompt-cache key unless the explicit raw-key flag is enabled

### Requirement: Proxy exposes runtime observability for bridge routing decisions

The service MUST expose metrics and structured logs for HTTP bridge routing decisions so operators can distinguish hard owner handoff from soft locality misses.

#### Scenario: owner forward metrics are emitted

- **WHEN** a hard continuity bridge request is forwarded to the owner replica
- **THEN** the service emits owner-forward counters for success or failure
- **AND** it records bridge forward latency

#### Scenario: soft locality misses are observable

- **WHEN** a prompt-cache bridge request lands on a non-owner replica and rebinds locally
- **THEN** the service emits locality miss and local rebind observability
- **AND** it logs a structured bridge event indicating soft locality rebind

### Requirement: Responses concurrency pressure is observable

The service MUST expose low-cardinality logs and metrics for account-local in-flight create count, active stream count, leased token/cost pressure, cap rejections, lease stale reclaims, soft-affinity reroutes, and local-vs-upstream 429 classification. Observability MUST avoid raw prompt text, raw affinity keys, API keys, and request payload content.

#### Scenario: Local and upstream 429s are separated

- **WHEN** local admission rejects a request and upstream later returns a rate limit for another request
- **THEN** logs and metrics distinguish local overload reasons from normalized upstream `upstream_rate_limit`
- **AND** preserved upstream wire payloads may retain upstream codes such as `rate_limit_exceeded`, `usage_limit_reached`, or `insufficient_quota`

### Requirement: Streaming timeout diagnostics are emitted

For `/v1/responses` HTTP/SSE streams, the service MUST log low-cardinality diagnostics for early heartbeat emission, keepalive emission, startup wait timeout, downstream disconnect, and stream idle timeout. The diagnostics MUST include request id, route family, account id when known, timeout stage, and elapsed seconds where available, without exposing payload content or raw affinity keys.

#### Scenario: Keepalive path is diagnosable

- **WHEN** a streaming Responses request waits for upstream events long enough to emit keepalive data
- **THEN** the service records heartbeat or keepalive diagnostics
- **AND** the diagnostic does not include raw prompt-cache keys or request payloads

### Requirement: HTTP bridge startup wait timeouts are logged

When an HTTP bridge startup wait times out locally, the service MUST log the request id, timeout stage, timeout seconds, and low-cardinality bridge affinity family. The log MUST NOT include raw prompt-cache keys, session ids, turn-state ids, API keys, or request payload content.

#### Scenario: Bridge startup admission timeout is diagnosable

- **WHEN** a HTTP bridge startup wait exceeds the configured proxy admission wait timeout
- **THEN** the console log includes the timeout stage and request id
- **AND** the log includes only low-cardinality affinity metadata, not raw affinity key values

### Requirement: Runtime continuity canary reports raw-error exposure and build parity
Operators MUST have a local verifier that reports whether the running `codex-lb` runtime is built from the expected code and whether recent Codex client logs contain raw `previous_response_not_found` errors.

#### Scenario: live runtime is checked after a continuity patch
- **WHEN** an operator runs the verifier on the Mac host
- **THEN** the verifier reports the repo commit, the running container image/id, local `/health` status, and recent raw `previous_response_not_found` count
- **AND** the verifier exits nonzero if raw errors are still present after the verification window
- **AND** the verifier redacts response ids by default unless `--show-ids` is passed

### Requirement: Request-log persistence failures are operator-visible
If request-log persistence fails for Responses WebSocket requests, the runtime MUST surface that condition in logs or verifier output so operators do not mistake HTTP `/health` success for continuity safety.

#### Scenario: request-log persistence fails during WebSocket traffic
- **WHEN** the runtime logs a request-log persistence failure
- **THEN** the verifier reports the failure count
- **AND** the continuity closeout cannot be marked green until persistence failures are absent or explicitly explained

### Requirement: Stale pending HTTP bridge retirement is logged

When the service retires an HTTP bridge session because pending precreated replay cannot make progress after upstream close or timeout, the service MUST emit a `retire_stale_pending` bridge event with low-cardinality bridge metadata and the terminal detail code.

#### Scenario: Failed precreated replay emits retirement event

- **WHEN** precreated HTTP bridge replay fails after upstream close or timeout
- **THEN** the console log includes a HTTP bridge event with `event=retire_stale_pending`
- **AND** the event includes only hashed bridge identity and low-cardinality metadata

### Requirement: Upstream 403 diagnostics include account-scoped recovery context

When proxy request handling or background model-registry refresh receives an upstream `403` that influences account selection or failover, the console log MUST include enough context to explain whether the failure was retried, cooled down, or surfaced.

#### Scenario: Websocket connect 403 log explains failover and cooldown

- **WHEN** a pre-commit upstream websocket connect fails with HTTP `403`
- **THEN** the console log includes the request id, transport, account id, model when known, HTTP status, normalized error code, upstream request identifier when present, and the chosen action (`failover_next` or `surface`)
- **AND** when a cooldown is applied, the log includes the cooldown duration

#### Scenario: Model refresh 403 log explains attribution

- **WHEN** background model-registry refresh receives HTTP `403`
- **THEN** the console log includes the account id, plan, HTTP status, upstream request identifier when present, and a bounded upstream response preview

### Requirement: Metrics expose recovery decisions for pre-commit failures

When Prometheus metrics are enabled, the service MUST expose counters for failover decisions, drain transitions, and client-exposed pre-commit upstream errors so operators can measure whether recovery paths are working.

#### Scenario: Pre-commit failover increments failover counter

- **WHEN** the proxy retries another eligible account before any downstream bytes are emitted
- **THEN** the failover counter increments with the transport and failure class labels for that decision

#### Scenario: Client-visible pre-commit error increments exposed-error counter

- **WHEN** the proxy must surface a pre-commit upstream failure because no more eligible accounts remain
- **THEN** the client-exposed error counter increments with the transport and normalized error code labels for that surfaced failure

### Requirement: Greenfield runtime baseline defines metrics and alerting coverage

When the greenfield runtime baseline is documented or enabled, the project MUST provide operator guidance for enabling metrics and alerting that covers readiness, process/container health, request success rate, request latency, upstream failure classes, stream timeout/incomplete errors, database lock pressure, and service-tier mismatches.

#### Scenario: Greenfield baseline metrics are enabled

- **WHEN** an operator follows the greenfield runtime baseline
- **THEN** the guidance enables or points to the metrics endpoint configuration
- **AND** the guidance identifies the scrape port and any required optional dependency or container setting

#### Scenario: Greenfield baseline alerts cover request quality

- **WHEN** an operator installs the recommended alerting bundle or copies the documented rules
- **THEN** alerts exist for elevated non-success request rate
- **AND** p95 latency or equivalent latency histogram degradation
- **AND** upstream timeout or stream_incomplete spikes

#### Scenario: Greenfield baseline alerts cover runtime health

- **WHEN** an operator installs the recommended alerting bundle or copies the documented rules
- **THEN** alerts exist for readiness failure, container restarts or OOM kills, database lock pressure, and bridge ownership or continuity error spikes

#### Scenario: Greenfield baseline exposes service-tier mismatch signal

- **WHEN** a request is made with requested service_tier ultrafast
- **AND** upstream reports actual response.service_tier as default or auto
- **THEN** metrics or documented request-log queries allow operators to count the mismatch without inspecting raw prompt data or secret-bearing logs

### Requirement: Performance triage separates local health from upstream latency

Operator-facing health or performance guidance MUST distinguish local proxy health from request-tail latency and upstream behavior. The guidance MUST combine process/container health, readiness checks, recent local error-log patterns, request latency percentiles, recent upstream failure classes, requested service tier, and actual upstream service tier before recommending a local code change, restart, worker-count change, or upstream/tier investigation.

#### Scenario: Healthy proxy has a slow request tail

- **WHEN** readiness checks pass
- **AND** the container has no recent restart, OOM, traceback, ASGI exception, or database-lock signal
- **AND** request logs still show elevated p90 or p95 latency
- **THEN** the guidance identifies the proxy as locally healthy
- **AND** it reports the latency tail separately from local health
- **AND** it does not recommend a local patch, restart, or worker-count change solely from the elevated latency percentile

#### Scenario: Requested tier differs from actual upstream tier

- **WHEN** request logs show `requested_service_tier` as `ultrafast`
- **AND** upstream responses report `actual_service_tier` as `default` or `auto`
- **THEN** the guidance treats the mismatch as an upstream/account/catalog verification issue first
- **AND** it does not require codex-lb to rewrite or downgrade the operator's requested tier

#### Scenario: Isolated upstream websocket failures occur amid successful traffic

- **WHEN** recent request logs contain isolated `stream_incomplete` or `upstream_websocket_open_timeout` rows
- **AND** later websocket requests for the same surface complete successfully
- **AND** local readiness and error-log checks remain clean
- **THEN** the guidance reports the failures as a caveat to monitor
- **AND** it does not classify the local proxy as unhealthy unless the failures become sustained or correlate with local runtime errors

### Requirement: Account usage depletion is observable via Prometheus

The system MUST export per-account Prometheus gauges for the latest known
usage percentage and seconds until window reset, labeled by account id and
usage window, updated whenever a usage refresh cycle persists or observes
fresh usage rows. Gauge label cardinality MUST be bounded by the number of
configured accounts and known usage windows.

#### Scenario: usage refresh updates depletion gauges

- **WHEN** the usage refresh scheduler completes a refresh cycle with a latest
  usage row for an account containing `used_percent` and `reset_at`
- **THEN** `codex_lb_account_usage_percent{account_id,window}` reports that
  `used_percent`
- **AND** `codex_lb_account_usage_reset_seconds{account_id,window}` reports the
  non-negative seconds remaining until `reset_at`

### Requirement: Transient account errors are counted by normalized code

The system MUST export a Prometheus counter of transient account errors
labeled by the normalized low-cardinality error code, incremented each time
the proxy records a transient error against an account. The label MUST NOT
contain request ids, account ids, or free-form upstream messages.

#### Scenario: websocket open timeout increments the counter

- **WHEN** an upstream websocket open timeout is recorded as a transient
  account error
- **THEN** `codex_lb_account_transient_errors_total{code="upstream_websocket_open_timeout"}`
  increments by one

