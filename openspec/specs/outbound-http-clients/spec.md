# outbound-http-clients Specification

## Purpose

Define outbound HTTP client behavior so upstream OAuth and API calls use stable headers, personas, and proxy handling.
## Requirements
### Requirement: OAuth authorize requests use a configurable originator persona
Browser OAuth authorize requests MUST include an `originator` query parameter. The service MUST default that parameter to `codex_chatgpt_desktop` and MUST let operators override it through configuration when they need a different first-party Codex persona.

#### Scenario: default OAuth authorize originator uses the Desktop persona
- **WHEN** the operator does not configure an override
- **THEN** the browser OAuth authorize URL includes `originator=codex_chatgpt_desktop`

#### Scenario: configured OAuth authorize originator falls back to the CLI persona
- **WHEN** the operator configures the OAuth authorize originator as `codex_cli_rs`
- **THEN** the browser OAuth authorize URL includes `originator=codex_cli_rs`

### Requirement: Upstream websocket handshakes auto-detect standard proxy environment variables

When operators don't explicitly configure `upstream_websocket_trust_env`, upstream websocket handshakes MUST honor standard outbound proxy environment variables before connecting directly.
Explicit configuration MUST still override auto-detection.

#### Scenario: secure websocket handshakes honor scheme-compatible env proxies by default

- **WHEN** an upstream websocket URL uses the `wss://` scheme
- **AND** `wss_proxy`, `socks_proxy`, `https_proxy`, or `all_proxy` is set
- **AND** `upstream_websocket_trust_env` is not explicitly configured
- **THEN** upstream websocket handshakes use the configured proxy instead of bypassing it

#### Scenario: plain websocket handshakes honor scheme-compatible env proxies by default

- **WHEN** an upstream websocket URL uses the `ws://` scheme
- **AND** `ws_proxy`, `socks_proxy`, `https_proxy`, `http_proxy`, or `all_proxy` is set
- **AND** `upstream_websocket_trust_env` is not explicitly configured
- **THEN** upstream websocket handshakes use the configured proxy instead of bypassing it

#### Scenario: ws handshakes preserve HTTPS proxy fallback

- **WHEN** an upstream websocket URL uses the `ws://` scheme
- **AND** `https_proxy` is set without a `ws_proxy` or `http_proxy` override
- **THEN** the upstream websocket handshake uses the `https_proxy` value before falling back to `all_proxy`

#### Scenario: explicit direct-connect override bypasses env proxies

- **WHEN** `upstream_websocket_trust_env=false`
- **AND** standard outbound proxy environment variables are set
- **THEN** upstream websocket handshakes connect directly without using those proxies

### Requirement: Runtime version status checks latest GitHub release

The service SHALL expose a dashboard-auth protected runtime version status API that reports the running codex-lb version, the latest known GitHub release version when available, whether an update is available, and the time of the latest lookup attempt. The lookup MUST be cached in-process to avoid per-request GitHub traffic, and lookup failures MUST NOT cause the API to fail.

#### Scenario: Latest release is newer than current version

- **WHEN** the running version is `1.19.0`
- **AND** the GitHub latest release tag is `v1.20.0`
- **THEN** the runtime version status reports `currentVersion: "1.19.0"`, `latestVersion: "1.20.0"`, and `updateAvailable: true`

#### Scenario: GitHub lookup fails

- **WHEN** the GitHub latest release lookup fails
- **THEN** the runtime version status API still returns the current version
- **AND** `updateAvailable` is `false`

### Requirement: Model refresh recovers from shared HTTP client transport failures

When the model registry refresh path fails before receiving an upstream HTTP response because of a transport-level error, the system MUST treat that failure as recoverable transport state, rebuild the shared outbound HTTP client, and retry the failed model-refresh operation at most once for the current failover cycle. HTTP status failures, invalid upstream payloads, and permanent authentication failures MUST NOT trigger shared-client rotation.

#### Scenario: model fetch transport failure rotates the shared client once

- **WHEN** a model refresh attempts to fetch upstream models for an active account
- **AND** the fetch fails with a timeout, `aiohttp.ClientError`, or OS-level transport error before an upstream HTTP response is received
- **THEN** the system rotates the shared outbound HTTP client
- **AND** retries the model fetch once with the replacement client
- **AND** does not perform additional client rotations for later transport errors in the same failover cycle

#### Scenario: token refresh transport failure also rotates the shared client once

- **WHEN** model refresh needs to refresh an account token before fetching models
- **AND** the token refresh fails with a timeout, `aiohttp.ClientError`, or OS-level transport error before an upstream HTTP response is received
- **THEN** the system rotates the shared outbound HTTP client
- **AND** retries the token refresh once with the replacement client
- **AND** preserves existing permanent/non-permanent refresh error classification for non-transport failures

### Requirement: Shared outbound HTTP client rotation preserves in-flight users

Callers that use the default shared outbound HTTP session or retry client MUST lease the current shared client for the full duration of their upstream operation. Rotating the shared client MUST make new callers use the replacement client while deferring closure of the retired client until all active leases on that retired client have released. Process shutdown MAY force-close active and retired clients to keep shutdown bounded.

#### Scenario: in-flight request keeps using retired client until release

- **WHEN** an upstream operation acquires a lease on the current shared client
- **AND** model refresh rotates the shared client after a transport failure
- **THEN** new shared-client callers use the replacement client
- **AND** the retired client remains open until the in-flight operation releases its lease

#### Scenario: long-lived operations hold one lease across their whole upstream exchange

- **WHEN** a shared-client caller performs a streaming response, compact request, transcription request, usage fetch, token refresh, OAuth call, model fetch, or file create/finalize poll loop
- **THEN** the caller holds a shared-client lease until the operation has finished consuming the upstream response or poll loop
- **AND** a concurrent shared-client rotation does not close that operation's client mid-exchange

#### Scenario: shutdown force-closes active leases

- **WHEN** the application is shutting down
- **AND** active leases still exist on the current or retired shared client
- **THEN** global HTTP client close is allowed to force-close those clients instead of waiting indefinitely for long-lived streams

### Requirement: Process-wide network failures rotate shared transport state

The service MUST classify local DNS resolver and host-route failures separately from account-specific upstream failures. Classification MUST come from typed exception provenance or an already-preserved stable internal code, not from matching arbitrary upstream message text. When such a failure affects the current shared outbound HTTP client, the service MUST make subsequent callers use a replacement client while preserving active leases on the retired client. Concurrent failures from the same retired generation MUST NOT cause repeated client rotations. Replacement construction and cleanup MUST remain cancellation-safe: an interrupted or failed replacement MUST close partially created resources and leave the previous generation current.

#### Scenario: DNS failure rotates the current shared client once

- **WHEN** concurrent outbound operations using the same shared client fail with a local DNS resolution error
- **THEN** the shared client is replaced once
- **AND** subsequent operations lease the replacement client
- **AND** active users of the retired client retain their lease until release

#### Scenario: Failure from a retired client does not rotate its replacement

- **WHEN** one caller has already replaced the shared client after a process-wide network failure
- **AND** another caller from the retired client reports the same failure
- **THEN** the replacement client remains current
- **AND** no additional replacement is created for that retired generation

#### Scenario: Upstream message text does not manufacture local provenance

- **WHEN** a genuine upstream failure uses `upstream_unavailable` and a message such as `Network is unreachable`
- **AND** no typed local-network classification accompanies it
- **THEN** the failure does not enter process-network recovery

#### Scenario: Cancelled replacement preserves the live generation

- **WHEN** shared-client replacement is cancelled after creating only part of the replacement transport
- **THEN** all partially created sessions and connectors are closed
- **AND** the previously current client generation remains current

### Requirement: Process-wide network failures are account neutral

The proxy MUST NOT record a transient, permanent, quota, rate-limit, or circuit-breaker health failure against an account when an attempt fails because the local process cannot resolve or route to the upstream host. Routed proxy transport failures MUST retain a credential-safe machine-readable classification after the original exception message is sanitized. A permanent missing proxy hostname MUST remain an endpoint-scoped proxy failure rather than entering process-wide recovery.

#### Scenario: Wi-Fi transition does not poison account health

- **WHEN** an upstream attempt fails with a classified local DNS or host-route failure
- **THEN** the selected account's health counters and cooldown state are unchanged
- **AND** the selected account's circuit breaker is unchanged
- **AND** continuity ownership remains pinned to that account

#### Scenario: Routed transient DNS failure remains account neutral after sanitization

- **WHEN** an HTTP or WebSocket attempt through a resolved upstream proxy route fails with transient DNS or local route loss
- **THEN** the credential-safe routed error carries the process-network classification
- **AND** the selected account's health and circuit-breaker state are unchanged

#### Scenario: Missing proxy hostname remains endpoint scoped

- **WHEN** resolving a configured upstream proxy hostname fails with a permanent name-not-found result
- **THEN** the failure remains `upstream_unavailable`
- **AND** the proxy does not classify the host process as disconnected

### Requirement: Routed streaming upstream responses are released when the consumer stops before EOF

When an upstream streaming request is issued through a resolved upstream proxy route, the response body is consumed unbuffered and the consumer routinely stops before the body reaches EOF: on the terminal stream event, on the stream idle timeout, on cancellation, on downstream disconnect, and when the response is mapped to an error before the body is drained. On every such exit the proxy MUST release or close the upstream response object before it closes the per-stream client that owns the connection, so the connection is returned or closed synchronously and no connection object is left to be finalized by the garbage collector.

The release MUST work for every response shape the routed path can receive: an aiohttp response (`release()`), a response that exposes only `close()` or only `aclose()` (those methods MUST be invoked), a SOCKS-owned wrapped response that MUST be released before the private session that carried it is closed, and a buffered or duck-typed response that exposes neither `release()`, `close()`, nor `aclose()` (no-op). Release MUST run only after the last event block has been yielded to the consumer and MUST NOT change the forwarded bytes, the error mapping, the retry classification, or the cancellation semantics of the stream.

#### Scenario: Terminal event arrives while upstream holds the connection open

- **GIVEN** a routed HTTP stream whose upstream emits `response.completed` and then keeps the connection open
- **WHEN** the proxy stops reading on the terminal event
- **THEN** the upstream response is released before the per-stream client is closed
- **AND** no `Unclosed connection` event is reported to the event loop exception handler after a full garbage collection
- **AND** the forwarded event blocks are byte-identical to the upstream frames

#### Scenario: Stream idle timeout

- **GIVEN** a routed HTTP stream whose upstream goes silent after the first event
- **WHEN** the stream idle timeout elapses
- **THEN** the synthetic `stream_idle_timeout` failure event is yielded as before
- **AND** the upstream response is released before the per-stream client is closed

#### Scenario: Cancellation or downstream disconnect mid-stream

- **GIVEN** a routed HTTP stream that is cancelled, or whose consumer calls `aclose()`, while a body read is pending
- **WHEN** the stream generator unwinds
- **THEN** the upstream response is released before the per-stream client is closed
- **AND** the cancellation propagates to the caller unchanged

#### Scenario: Error status mapped before the body is drained

- **GIVEN** a routed HTTP stream whose upstream answers with a non-2xx status
- **WHEN** the proxy raises the mapped `ProxyResponseError`
- **THEN** the upstream response is released before the per-stream client is closed

#### Scenario: Close-only or aclose-only response is released

- **GIVEN** a routed response object that exposes only `close()` or only `aclose()`
- **WHEN** the stream ends
- **THEN** that method is invoked before the per-stream client is closed

#### Scenario: Response without a release method

- **GIVEN** a routed response object that exposes neither `release()`, `close()` nor `aclose()`
- **WHEN** the stream ends
- **THEN** teardown is a no-op for the response and the stream result is unchanged

### Requirement: Routed aiohttp egress carries proxy credentials outside the proxy URL

When the Codex upstream client dispatches a routed HTTP request or WebSocket connect through aiohttp, it MUST pass a credential-free proxy URL (`scheme://host:port`) and MUST carry the endpoint username and password as a `Proxy-Authorization` Basic header whose bytes are identical to the header aiohttp derives from URL userinfo (latin1 encoding). The client MUST NOT place proxy credentials in the aiohttp proxy URL. Because aiohttp forwards proxy headers only on the CONNECT tunnel, a route whose ordered pool contains any credentialed endpoint MUST fail closed for a non-TLS (`http`/`ws`) upstream target before any connection is opened and ahead of every transport branch (aiohttp and SOCKS), surfacing as a credential-free connect-phase transport error, so a credential-free fallback endpoint cannot absorb the misconfigured primary. Route resolution MUST fail closed for an `http` or `https` proxy username containing `:`. SOCKS5/SOCKS5H RFC 1929 usernames MAY contain `:`. SOCKS transports keep carrying credentials through their existing field inputs. HTTP/SOCKS endpoints MAY still store credentials; aiohttp dispatch MUST still pass a credential-free proxy URL.

#### Scenario: Credentialed https endpoint uses Proxy-Authorization

- **GIVEN** a resolved `https` proxy endpoint with a username and password
- **WHEN** the Codex upstream client sends a routed request or opens a routed WebSocket through aiohttp
- **THEN** the aiohttp `proxy` argument contains no userinfo
- **AND** the CONNECT request carries a `Proxy-Authorization` header whose value is byte-identical to the userinfo-derived token
- **AND** the aiohttp connection-key repr and the proxy-error message text contain neither the password nor its Basic token
- **AND** the proxy-error repr, which carries the tunnel request headers, renders with `Basic [REDACTED]` through the log formatters

#### Scenario: Credentialed route to a plaintext target fails closed

- **GIVEN** a resolved route whose primary proxy endpoint carries credentials and whose fallback does not
- **WHEN** the Codex upstream client is asked to reach an `http` or `ws` upstream URL, for an idempotent or non-idempotent request or a WebSocket open
- **THEN** the client fails before dispatch with a credential-free connect-phase transport error
- **AND** no endpoint in the pool, including the credential-free fallback, receives the request on any transport

#### Scenario: HTTP username with a colon is rejected at resolution

- **WHEN** an `http` or `https` proxy endpoint username contains `:`
- **THEN** route resolution fails closed with reason `invalid_proxy_username`

#### Scenario: SOCKS username with a colon is accepted at resolution

- **WHEN** a `socks5` or `socks5h` proxy endpoint username contains `:`
- **THEN** route resolution succeeds and preserves the username

### Requirement: Dashboard rejects and reports proxy usernames the resolver cannot encode

The dashboard MUST reject an `http` or `https` upstream proxy endpoint whose username contains `:` at creation with a 400 error coded `invalid_proxy_username`, mirroring the resolver rule (RFC 7617 Basic credentials cannot encode a colon in the user-id). SOCKS5/SOCKS5H RFC 1929 usernames MAY contain `:`. The endpoint test route MUST report a resolver rejection of an already persisted endpoint as a failed probe carrying the resolver reason rather than surfacing an unhandled error.

#### Scenario: HTTP colon username is rejected at creation

- **WHEN** an operator creates an `http` or `https` upstream proxy endpoint whose username contains `:`
- **THEN** the request is rejected with a 400 error coded `invalid_proxy_username`

#### Scenario: SOCKS colon username is accepted at creation

- **WHEN** an operator creates a `socks5` or `socks5h` upstream proxy endpoint whose username contains `:`
- **THEN** the endpoint is created and the username is preserved

#### Scenario: Endpoint test reports a persisted row the resolver rejects

- **GIVEN** a persisted endpoint the resolver rejects (for example an HTTP username containing `:`)
- **WHEN** the endpoint test route is invoked for it
- **THEN** the response reports `ok: false` with the resolver reason as `error` and no status code
- **AND** no probe is sent
