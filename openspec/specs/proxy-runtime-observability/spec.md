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

When the proxy resolves or fails closed a continuity-sensitive follow-up request, the system MUST emit structured diagnostics that let operators determine how continuity ownership was resolved or why the proxy returned a retryable masked error.

#### Scenario: owner resolution source is recorded for a previous-response follow-up

- **WHEN** a websocket, HTTP fallback, or HTTP bridge follow-up request includes `previous_response_id`
- **AND** the proxy resolves the required owner account from a continuity source such as a local bridge session, owner cache, or request-log lookup
- **THEN** the system emits a structured diagnostic describing the continuity surface, source, and outcome
- **AND** the diagnostic does not expose the raw `previous_response_id`

#### Scenario: fail-closed continuity masking is recorded

- **WHEN** the proxy rewrites or returns a retryable continuity error because owner metadata is unavailable, continuity state is lost, or the pinned owner account is unavailable
- **THEN** the system emits a structured diagnostic describing the continuity surface and fail-closed reason
- **AND** Prometheus counters record the low-cardinality source or reason labels for that decision

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
