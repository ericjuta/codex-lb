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

When resolving or failing closed a continuity-sensitive follow-up, the system MUST emit structured diagnostics identifying ownership resolution or the retryable masked error's reason. When an upstream error payload is available, the structured fail-closed log MUST include its normalized `upstream_error_code`, captured before rewriting.

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

The proxy MUST offer an opt-in durable Codex-to-upstream conversation archive. When enabled, it MUST write gzip JSONL for upstream request payloads, streamed Responses events, compact response payloads, and websocket text or binary frames. Normal operation MUST keep gzip file I/O outside the request event loop. The writer queue MUST be bounded and apply synchronous write backpressure when the background writer is saturated.

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

### Requirement: Process-wide network recovery is observable without sensitive resolver data

The service MUST emit low-cardinality structured diagnostics when it detects a process-wide DNS or route failure, rotates shared transport state, retries a safe request, recovers, or exhausts the request budget. Diagnostics MUST NOT contain DNS server addresses, request payloads, API keys, access tokens, raw continuity keys, or account email addresses.

#### Scenario: Recovery diagnostics are emitted

- **WHEN** a safe Responses request enters and later exits process-wide network recovery
- **THEN** logs identify the recovery stage, request id, transport, attempt count, and internal account id when known
- **AND** logs do not expose resolver configuration or request content

#### Scenario: Concurrent rotation is coalesced visibly

- **WHEN** several callers report a network failure from the same shared client generation
- **THEN** diagnostics distinguish the caller that rotated the client from callers that reused the already-rotated replacement

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

### Requirement: Service-tier mismatches use successful terminal evidence
The service-tier mismatch counter MUST count only successful requests whose explicit nonblank terminal tier differs from the normalized requested tier. Created/in-progress tiers, requested-tier fallbacks, missing terminal tiers, and unsuccessful attempts MUST NOT increment it. Existing counter coverage and bounded labels MUST remain, without identities or payload data.

#### Scenario: Explicit terminal default differs from requested priority
- **WHEN** a successful counted request asks for `priority` and completes with explicit `default`
- **THEN** one mismatch is counted with requested `priority` and actual `default`

#### Scenario: Created auto followed by terminal priority is not a mismatch
- **WHEN** a successful counted request asks for `priority`, starts with created `auto`, and completes with explicit `priority`
- **THEN** the created tier does not increment the mismatch counter

#### Scenario: Missing terminal tier does not count a created fallback
- **WHEN** a counted request starts with a tier different from the requested tier but completes without a tier
- **THEN** the request does not increment the mismatch counter

#### Scenario: Failure does not count a tier mismatch
- **WHEN** a counted attempt fails, is cancelled, disconnects, or finishes incomplete
- **THEN** it does not increment the mismatch counter even if an earlier event included a different tier

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

### Requirement: Request metric labels have bounded cardinality

Request counter and duration metrics MUST use bounded labels:

- `method`: preserve `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, and `OPTIONS`. Map all other methods to `OTHER`.
- `path`: preserve existing `/v1/...`, `/api/...`, `/health/...`, and bare `/health` values. Collapse `/backend-api/` paths to `/backend-api/...` and `/internal/` paths to `/internal/...`. Map all other paths to `/other`.

Labels MUST NOT contain raw or truncated unmatched paths.

#### Scenario: Unmatched paths share one metric label

- **WHEN** requests use distinct paths outside the `/v1/`, `/api/`, `/health/`, `/backend-api/`, and `/internal/` prefixes, including SPA-looking paths
- **THEN** request counter and duration metrics use `path="/other"` for every such request
- **AND** no raw unmatched path or truncated unmatched path becomes a metric label value

#### Scenario: Primary proxy paths use bounded labels

- **WHEN** requests use `/backend-api/codex/responses`, dynamic `/backend-api/files/{file_id}/uploaded`, or `/internal/bridge/...` paths
- **THEN** request counter and duration metrics use `/backend-api/...` for every `/backend-api/` path and `/internal/...` for every `/internal/` path
- **AND** no dynamic file ID or other raw suffix becomes a metric label value

#### Scenario: Unsupported methods share the OTHER label

- **WHEN** a request uses an HTTP method outside the supported method vocabulary
- **THEN** request counter and duration metrics use `method="OTHER"`

#### Scenario: Existing collapsed paths remain stable

- **WHEN** a request uses a path under `/v1/`, `/api/`, or `/health/`, or uses bare `/health`
- **THEN** the metric path label retains its existing value

### Requirement: Rendered log records redact URL userinfo and keyed secrets

The application's text, access, and JSON formatters MUST redact every logger's records, including exception and stack text. They MUST replace `scheme://user:password@` and `scheme://user@` with `scheme://[REDACTED]@`, and `Basic <token>` with `Basic [REDACTED]` for `Basic`, `basic`, and `BASIC` spellings. Structured extra keys MUST be redacted like values.

#### Scenario: Unclosed aiohttp connection repr is credential-free

- **GIVEN** an aiohttp connection is finalized without release and its connection key holds a credentialed proxy URL
- **WHEN** the loop exception handler logs `Unclosed connection` through the `asyncio` logger
- **THEN** the rendered record contains `proxy=URL('scheme://[REDACTED]@host:port')`
- **AND** the password appears in neither the text nor the JSON rendering

#### Scenario: Userinfo containing unencoded sub-delims is redacted

- **GIVEN** a proxy password containing an RFC 3986 sub-delim such as `'`, which yarl leaves unencoded in the URL userinfo, or a raw environment proxy string that is not percent-encoded at all
- **WHEN** the URL is rendered in any log record at any level
- **THEN** the record contains `scheme://[REDACTED]@host:port` and neither the raw nor the percent-encoded password

#### Scenario: Username-only URL userinfo is redacted

- **GIVEN** a URL whose userinfo carries only a username (`scheme://user@host:port`) with no `:password` part
- **WHEN** the URL is rendered in any log record at any level, text or JSON
- **THEN** the record contains `scheme://[REDACTED]@host:port` and the username does not appear

#### Scenario: Proxy error repr with a Basic token is masked

- **GIVEN** an aiohttp proxy error whose tunnel request headers carry `Proxy-Authorization: Basic <token>`
- **WHEN** the error is logged with `%r` at any level, or its repr is logged by the loop's exception handler for an unretrieved task
- **THEN** the rendered record contains `'Proxy-Authorization': 'Basic [REDACTED]'`
- **AND** neither the token nor the password appears in the text or JSON rendering

#### Scenario: Secret-keyed structured extras are masked

- **GIVEN** a WARNING or higher record carries an extra field such as `{"password": "..."}` or `{"access_token": "..."}`
- **WHEN** the JSON formatter renders the record
- **THEN** the field value is replaced with `[REDACTED]` whatever its type (string, list, number, bytes, mapping); a null value stays null
- **AND** fields such as `attempt` or `tokens` keep their values
- **AND** an extra key carrying URL userinfo is rendered as `scheme://[REDACTED]@host`

#### Scenario: Secret-free records are unchanged

- **WHEN** a record such as the one-time bootstrap token banner contains no URL userinfo or keyed secret pattern
- **THEN** the rendered output is byte-identical to the unredacted rendering

#### Scenario: Redaction failure never breaks logging and fails closed

- **WHEN** a redaction pass raises while rendering a record
- **THEN** the record is still emitted, in text and JSON, with its timestamp, level and logger
- **AND** the affected text is rendered as `[REDACTED: log redaction failed]` rather than the original text

#### Scenario: Cyclic or unprintable structured extras never drop the record

- **GIVEN** a record carries an extra whose container refers back to itself, or whose `repr()` raises
- **WHEN** the JSON formatter renders the record
- **THEN** the record is emitted, the back-reference collapses to a `{...}` / `[...]` placeholder and the unprintable value to an `<unprintable ...>` marker
- **AND** secret-keyed fields and URL userinfo in the finite part of the extra are still redacted

#### Scenario: Secret-keyed mappings rendered as Python repr are masked

- **GIVEN** a WARNING or higher record renders a mapping with `%r`, or the JSON formatter falls back to text for a structured extra
- **WHEN** the rendered text contains `'password': 'x'`, `'access_token': [...]` or `'api_key': 123`
- **THEN** each secret-keyed value is replaced with `[REDACTED]` (quotes kept for quoted strings)
- **AND** `'Proxy-Authorization': 'Basic <token>'` keeps rendering as `'Basic [REDACTED]'`

### Requirement: Secret-pattern redaction stays on the current line

Keyed, bearer, basic, authorization, JSON, and Python-repr secret patterns MUST apply per CR/LF-delimited log line. Matches MUST NOT consume CR, LF, or text from later lines. Redaction MUST cover unterminated JSON secrets through line end and same-line glued `:` tails on Bearer credentials. Comma and ampersand separators MUST retain existing same-line truncation behavior. Records below WARNING MUST still skip these keyed patterns.

#### Scenario: Authorization does not swallow the next traceback line

- **GIVEN** a WARNING or higher record whose exception text contains `authorization=Basic X` followed by a newline and `status=failed`
- **WHEN** the text or JSON formatter renders the record
- **THEN** the Basic credential is replaced with `[REDACTED]`
- **AND** the following line still contains `status=failed`

#### Scenario: Unterminated JSON secret is redacted through end of line

- **GIVEN** a WARNING or higher record contains `{"token":"abc` with no closing quote before the line ending, then a following `safe diagnostic line`
- **WHEN** the text or JSON formatter renders the record
- **THEN** the token value is replaced with `[REDACTED]`
- **AND** `safe diagnostic line` remains

#### Scenario: Bearer glued colon tail is redacted

- **GIVEN** a WARNING or higher record contains `Bearer abc.def:GLUEDTAIL, status=502`
- **WHEN** the text or JSON formatter renders the record
- **THEN** the rendered text contains `Bearer [REDACTED], status=502`
- **AND** neither `abc.def` nor `GLUEDTAIL` appears

#### Scenario: Same-line authorization truncation is unchanged

- **GIVEN** a WARNING or higher record contains `Authorization: Basic dXNlcjpwYXNz status=failed` on one line with no comma
- **WHEN** the text formatter renders the record
- **THEN** the credential is redacted
- **AND** `status=failed` is not present on that line

#### Scenario: Line terminators are preserved and redaction is idempotent

- **GIVEN** rendered secret-bearing text that uses LF and CRLF separators
- **WHEN** secret-pattern redaction is applied once and then again
- **THEN** the terminator bytes and line count are unchanged
- **AND** the second pass equals the first

### Requirement: Loop exception handler output redacts context value reprs

Startup MUST idempotently install an asyncio loop exception handler. Before delegating to the previous or default handler, it MUST sanitize `message` and redact `repr()` for every other context value the default handler would render. Secret-free output MUST match the default handler byte-for-byte. A value whose `repr()` raises MUST become an opaque stand-in.

#### Scenario: Unclosed aiohttp connection repr is credential-free before logging

- **GIVEN** an aiohttp connection is finalized without release and its connection key holds a credentialed proxy URL
- **WHEN** the loop exception handler receives `Unclosed connection` with the connection object in its context
- **THEN** the `asyncio` log record already contains `proxy=URL('scheme://[REDACTED]@host:port')`
- **AND** the password appears nowhere in the record, independent of the formatter in use, including passwords carrying sub-delims such as `'` that yarl leaves unencoded

#### Scenario: Unretrieved task exception repr is redacted

- **WHEN** a task whose exception text or repr carries URL userinfo or a `Basic <token>` header is garbage-collected unretrieved
- **THEN** the `Task exception was never retrieved` record renders the task repr with `[REDACTED]` in place of the credential

#### Scenario: Secret-free contexts and failures are transparent

- **WHEN** the context contains no secret pattern
- **THEN** the emitted record message and exception info are byte-identical to the default handler output
- **WHEN** a handler was already installed
- **THEN** the previously installed handler still receives the (redacted) context
- **WHEN** a context value's `repr()` raises
- **THEN** the record is still emitted with its `message` line intact and that value rendered as an opaque stand-in naming the value type and the exception type
- **WHEN** the previous handler or default fallback raises `CancelledError` or another `BaseException` other than `KeyboardInterrupt` or `SystemExit`
- **THEN** the sanitized context is still emitted with a fixed `Unhandled error in exception handler` record and the exception is not rethrown
- **WHEN** the redaction pass itself fails
- **THEN** the record is still emitted with a sanitized `message` and opaque stand-ins
- **AND** `exception`, `source_traceback`, and `handle_traceback` are omitted

### Requirement: Tool-linkage diagnostics distinguish corruption variants

Upstream tool-linkage fail-closed diagnostics MUST label a call whose output never arrived as `missing_tool_output` (`"No tool output found for function call call_..."`). They MUST label an output whose call is absent from the resolved previous-response context as `orphaned_tool_output` (`"No tool call found for function call output with call_id ..."`).

#### Scenario: Missing output retains its distinct label

- **WHEN** upstream reports `"No tool output found for function call call_X"`
- **THEN** fail-closed diagnostics label the failure `missing_tool_output`

### Requirement: Tool-linkage labels preserve continuity recovery behavior

Both tool-linkage corruption variants MUST retain the client-visible `stream_incomplete` (`server_error`) envelope. Variant labeling MUST NOT change reconnect-request, grouped-terminal, or rewrite behavior from the prior single `missing_tool_output` classification.

#### Scenario: Variant labeling does not change recovery

- **WHEN** upstream tool-linkage corruption is labeled `orphaned_tool_output`
- **THEN** reconnect-request, grouped-terminal, and rewrite behavior remain the same as under the prior single `missing_tool_output` classification

### Requirement: Archive records retain metadata and redact credentials

Archive records MUST include request id, timestamp, direction, traffic kind, transport, account id when known, upstream target metadata, redacted headers, and full payload or frame body. Credential-bearing headers, including authorization, cookies, proxy authorization, token headers, and API key headers, MUST be redacted before persistence. Non-ASCII payload text MUST remain UTF-8, not Unicode escapes. When disabled, the writer MUST NOT create archive files.

#### Scenario: Archive persistence preserves content without header credentials

- **WHEN** the enabled writer persists a record with non-ASCII payload text and credential-bearing headers
- **THEN** it retains the full body and required metadata, stores non-ASCII text as UTF-8, and redacts the headers before persistence

### Requirement: Service-tier reporting avoids unsupported scheduling conclusions

Explicit `auto` MUST remain observable as the reported tier. Guidance MUST describe it as inconclusive for Fast delivery, not proof of downgrade. Counter equality or absence MUST NOT be presented as upstream scheduling evidence.

#### Scenario: Explicit auto is inconclusive for Fast delivery

- **WHEN** upstream explicitly reports `auto`
- **THEN** it remains the observable tier and guidance does not treat it as proof of downgrade

### Requirement: Warning logs redact keyed secrets

At WARNING or higher, application text, access, and JSON formatters MUST also redact `password=`, `token=`, `api_key=`, case-insensitive bearer/basic/authorization values, JSON secret fields embedded in strings, and secret-keyed structured extras of any value type.

#### Scenario: Warning secrets are removed across renderers

- **WHEN** a WARNING record contains keyed secrets in text or structured extras
- **THEN** text, access, and JSON formatters redact them regardless of their value type

### Requirement: Log redaction failures preserve sanitized records

Redaction MUST never raise. Failed passes MUST replace affected text with `[REDACTED: log redaction failed]` and still emit the timestamp, level, and logger. Cyclic, pathologically deep, or unprintable extras MUST still be emitted with every finite, printable part redacted. Secret-free records MUST render byte-identically to unredacted output.

#### Scenario: Deep structured extras retain finite redacted content

- **WHEN** a log record contains pathologically deep structured extras
- **THEN** the record is emitted with redaction applied to every finite, printable part

### Requirement: Startup routes warnings through application logging

Application startup MUST route `warnings.warn` through the same log handlers. Both `install_redacting_loop_exception_handler` and application lifespan MUST call `logging.captureWarnings(True)` so uvicorn workers inherit the same handlers.

#### Scenario: Workers capture warnings through redacting handlers

- **WHEN** application lifespan or loop exception handler installation runs
- **THEN** it calls `logging.captureWarnings(True)` and warnings use the application log handlers

### Requirement: Loop exception snapshots remove secret causes and context

If redaction changes an exception's `str()`, `repr()`, or formatted traceback, the loop exception handler MUST replace it with a secret-free snapshot without raw cause or context. `source_traceback` and `handle_traceback` MUST use formatted-text redaction.

#### Scenario: Secret exception snapshot has no raw cause

- **WHEN** redaction changes an exception's formatted traceback
- **THEN** the handler delegates a secret-free snapshot without raw cause or context

### Requirement: Loop exception delegate failures emit sanitized context

The previous handler and default fallback MUST catch `BaseException`, including `CancelledError`, except `KeyboardInterrupt` and `SystemExit`. They MUST emit sanitized context plus a fixed `Unhandled error in exception handler` record without rethrowing.

#### Scenario: Cancelled delegate still emits sanitized diagnostics

- **WHEN** the previous handler or default fallback raises `CancelledError`
- **THEN** sanitized context and `Unhandled error in exception handler` are emitted without rethrowing

### Requirement: Loop redaction failures omit unsafe traceback context

Fail-closed reports MUST omit `exception`, `source_traceback`, and `handle_traceback`, retaining only sanitized `message` and opaque stand-ins for other values. Unredacted values MUST NOT reach the delegate.

#### Scenario: Redaction failure excludes raw context

- **WHEN** loop context redaction fails
- **THEN** the delegate receives only sanitized `message` and opaque stand-ins, without exception or traceback fields

