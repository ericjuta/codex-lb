# proxy-admission-control Specification

## Purpose
Define how the proxy protects itself under load while preserving short request paths and surfacing local overload clearly.
## Requirements
### Requirement: Downstream proxy admission is split by traffic class

The system MUST enforce independent downstream admission limits for proxy HTTP requests, proxy websocket sessions, compact HTTP requests, and dashboard traffic. Exhausting one proxy lane MUST NOT consume capacity from the others.

#### Scenario: Websocket session load does not starve HTTP responses
- **WHEN** the proxy websocket admission lane is full
- **THEN** new websocket sessions are rejected locally
- **AND** eligible proxy HTTP requests may still proceed if their own lane has capacity

#### Scenario: Compact lane survives general proxy load
- **WHEN** the general proxy HTTP lane is saturated
- **AND** the compact lane still has capacity
- **THEN** `/backend-api/codex/responses/compact` and `/v1/responses/compact` requests continue to be admitted

### Requirement: Local overload responses are explicit

When the proxy rejects a request locally because an admission lane or expensive-work stage is full, it MUST return a local-overload response with a `Retry-After` header. HTTP requests MUST use an OpenAI-style error envelope and websocket handshake denials MUST use an HTTP denial response instead of a pre-accept close frame.

#### Scenario: HTTP admission rejection returns explicit overload envelope
- **WHEN** a proxy HTTP request is rejected locally for overload
- **THEN** the response status is `429`
- **AND** the response includes `Retry-After`
- **AND** the error payload identifies the failure as local proxy overload instead of upstream unavailability

#### Scenario: Websocket handshake rejection returns explicit overload status
- **WHEN** a websocket handshake is rejected locally for overload
- **THEN** the client receives an HTTP denial response with the real overload status
- **AND** the server access log reflects that overload status instead of `403 Forbidden`

### Requirement: Expensive upstream work is admission controlled

The proxy MUST enforce separate in-process admission limits for token refresh, upstream websocket connect, and first-turn response creation.

#### Scenario: Token refresh admission rejects excess work
- **WHEN** concurrent forced token refresh work reaches the configured refresh limit
- **THEN** additional refresh attempts are rejected locally with an explicit overload response

#### Scenario: Response creation admission releases after first upstream acceptance
- **WHEN** the proxy is waiting for an upstream response to be created
- **THEN** that request holds a response-create admission slot
- **AND** the slot is released when the request receives `response.created` or fails before creation completes

### Requirement: Account-local Responses work is capped before upstream creation

For `/v1/responses`, `/backend-api/codex/responses`, and compact Responses traffic, the proxy MUST enforce account-local response-create and streaming concurrency limits in addition to process-wide admission limits. The default account response-create cap MUST be 4 and the default account stream cap MUST be 8 unless operators configure a different value. When an account is at either cap, new soft-affinity work MUST prefer another eligible account before returning local overload. Hard-continuity work MAY fail closed when the required owner account is saturated.

#### Scenario: Soft work avoids saturated account

- **GIVEN** account A is at its account response-create cap
- **AND** account B is eligible and below cap
- **WHEN** a soft-affinity `/v1/responses` request is routed
- **THEN** the proxy selects account B instead of queueing on account A

#### Scenario: Hard continuity owner saturation fails closed

- **GIVEN** a follow-up request requires a specific previous-response owner account
- **AND** that account is at its account stream or response-create cap
- **WHEN** no safe continuity-preserving alternative exists
- **THEN** the proxy returns a bounded local overload/continuity failure
- **AND** the failure reason is stable and low-cardinality

### Requirement: Local overload reasons are stable and distinguishable

Local Responses overload failures MUST expose stable low-cardinality reason fields in logs and metrics so operators can distinguish `bridge_queue_full`, `response_create_gate_timeout`, `hard_affinity_saturated`, `previous_response_owner_unavailable`, `global_admission_timeout`, `capacity_exhausted_active_sessions`, `account_response_create_cap`, and `account_stream_cap`. These local reasons MUST NOT be reported as upstream rate limits.

#### Scenario: Bridge queue saturation is not ambiguous

- **WHEN** a local HTTP bridge queue rejects a request
- **THEN** logs and metrics use the stable reason `bridge_queue_full`
- **AND** they do not use the ambiguous alias `queue_full`

#### Scenario: Queued bridge requests wait for the response-create gate within the request budget

- **WHEN** a visible HTTP bridge request has already claimed a bridge queue slot
- **AND** the per-session `response_create_gate` is held by legitimate in-flight work
- **THEN** each gate acquisition attempt waits until the configured `proxy_admission_wait_timeout_seconds` elapses
- **AND** expired attempts re-enter a recoverable capacity wait bounded by the bridge request budget instead of failing terminally
- **AND** `response_create_gate_timeout` remains the stable reason when the budget is exhausted
- **AND** `bridge_queue_full` remains the bounded local-overload reason when the bridge queue itself is saturated

#### Scenario: Account cap rejection is local overload

- **WHEN** every eligible account is unavailable because of account-local caps
- **THEN** the HTTP response is a local overload response with `Retry-After`
- **AND** logs and metrics identify `account_response_create_cap` or `account_stream_cap`

### Requirement: HTTP bridge startup admission waits are bounded

The proxy MUST apply the configured proxy admission wait timeout to each HTTP bridge startup wait attempt for per-session response-create gate acquisition, bridge capacity waiters, and in-flight session creation waiters.

For per-session response-create gate acquisition by a bridged Responses request, an expired gate acquisition attempt MUST be treated as a recoverable capacity wait rather than a terminal failure: the request MUST release its queue slot and account lease, wait with capacity-wait progress semantics, and retry gate acquisition, bounded by the bridge request budget. Requests eligible for soft-affinity reroute MUST still attempt the reroute before entering the recoverable wait. When the bridge request budget is exhausted before the gate opens, the proxy MUST reject the request locally with HTTP 429, `error.code = "response_create_gate_timeout"`, and the stable local-overload reason.

For bridge capacity waiters and in-flight session creation waiters, when the timeout expires the proxy MUST reject the request locally with HTTP 429 and an OpenAI-style `proxy_overloaded` error envelope. Timing out while observing another request's pending in-flight session creation MUST evict that in-flight marker when it is still pending so later requests can attempt a fresh bridge session instead of waiting on the same stalled future.

If a request owns in-flight bridge session creation and is cancelled or fails after publishing the in-flight marker but before registering the created session, the proxy MUST remove or settle that in-flight marker. If a session owner later finishes creation after its in-flight marker was evicted, the owner MUST NOT return an unregistered bridge session to the caller.

#### Scenario: Gate contention queues within the bridge request budget

- **GIVEN** an HTTP bridge session whose response-create gate is held by a legitimate in-flight turn
- **AND** a bridged Responses request that cannot soft-reroute (hard-affinity key or `previous_response_id` continuity)
- **WHEN** a gate acquisition attempt exceeds the configured proxy admission wait timeout
- **THEN** the request emits capacity-wait keepalive progress on streaming surfaces and retries gate acquisition
- **AND** the request completes normally once the in-flight turn releases the gate before the bridge request budget expires

#### Scenario: Gate contention still fails once the request budget is exhausted

- **WHEN** a bridged Responses request retries response-create gate acquisition until the bridge request budget is exhausted
- **THEN** the request is rejected locally with HTTP 429
- **AND** the error payload uses `error.code = "response_create_gate_timeout"`
- **AND** no response-create gate lease is recorded on that request state

#### Scenario: Soft-affinity requests reroute before waiting

- **GIVEN** a bridged Responses request with a soft-affinity session key and no `previous_response_id`
- **WHEN** its first gate acquisition attempt times out
- **THEN** the proxy attempts the internal soft-affinity reroute to a fresh bridge session
- **AND** the recoverable gate wait applies only when reroute is not permitted

#### Scenario: Stuck sessions are still detected between attempts

- **WHEN** a gate acquisition attempt times out while a pending bridge request has been stuck past the stuck-gate retirement threshold
- **THEN** the stuck session retirement check still runs on that attempt

#### Scenario: In-flight bridge session creation does not finish

- **WHEN** a bridged Responses request waits on another request's in-flight session creation
- **AND** the in-flight creation does not finish before the configured proxy admission wait timeout
- **THEN** the waiter is rejected locally with HTTP 429 and `error.code = "proxy_overloaded"`
- **AND** the stalled in-flight marker is evicted if it is still pending

#### Scenario: Bridge capacity waiter does not make progress

- **WHEN** the HTTP bridge is at capacity and a request waits for in-flight bridge work to free capacity
- **AND** no capacity becomes available before the configured proxy admission wait timeout
- **THEN** the waiter is rejected locally with HTTP 429 and `error.code = "proxy_overloaded"`

#### Scenario: In-flight owner is cancelled during stale session close

- **WHEN** a bridge session creation owner has published an in-flight marker
- **AND** it is cancelled while closing a stale local bridge session before creating the replacement session
- **THEN** the in-flight marker is removed or settled
- **AND** later requests do not remain blocked on that cancelled owner's future

### Requirement: Stuck HTTP bridge response-create gate sessions are retired

The proxy MUST retain the existing waiter-triggered retirement behavior for stale HTTP bridge response-create gate owners and MUST additionally enforce an owner-side deadline for a visible HTTP request whose current upstream `response.create` send remains completely eventless before `response.created`. The owner-side deadline MUST be measured from a monotonic timestamp recorded immediately before the current upstream send, MUST use the smaller of the configured stuck-gate retirement threshold and 240 seconds, MUST run without a second gate waiter, and MUST remain active when periodic SSE keepalives are disabled.

The owner-side watchdog MUST apply only while the request owns the response-create gate, awaits `response.created`, has neither a response id nor recorded `response.created` latency, has received no matched `response.*` lifecycle event, and has produced no downstream-visible output or sequence evidence. Non-response telemetry such as `codex.rate_limits` MUST NOT suppress this watchdog. Any matched `response.*` lifecycle event, response-created milestone, or downstream-visible evidence MUST suppress the owner-side watchdog and leave existing timeout behavior unchanged.

When the owner-side deadline expires, the proxy MUST recheck eligibility, emit a structured low-cardinality log and the existing stuck-retirement Prometheus counter, terminally fail and settle every pending request exactly once, and retire the whole bridge session. It MUST NOT transparently replay the timed-out request, move it to another account, or write an account-health failure for the missing-created timeout.

#### Scenario: Lone eventless gate owner is retired before the client timeout

- **GIVEN** a visible HTTP bridge request owns the response-create gate
- **AND** its current `response.create` send produced no matched `response.*` event, response id, or downstream-visible output
- **AND** no second request waits for the gate
- **WHEN** the smaller of the configured stuck threshold and 240 seconds elapses after the current send
- **THEN** the proxy emits an explicit terminal failure and retires the bridge session
- **AND** recovery occurs before the native client's 300-second parsed-event idle timeout

#### Scenario: Send time rather than request age anchors the deadline

- **GIVEN** a request spends most of its budget waiting for admission before it sends `response.create`
- **WHEN** the upstream send succeeds
- **THEN** the owner-side deadline begins from that current send
- **AND** earlier queue or admission time does not make the request immediately stale

#### Scenario: Leading telemetry does not mask an eventless owner

- **GIVEN** a pre-created gate owner receives `codex.rate_limits` but no matched `response.*` lifecycle event
- **WHEN** the owner-side deadline elapses
- **THEN** the telemetry does not refresh or suppress the deadline
- **AND** the proxy fails and retires the session

#### Scenario: Response lifecycle evidence suppresses the narrow watchdog

- **GIVEN** a pre-created request receives any matched `response.*` lifecycle event, a response id, recorded `response.created` latency, or downstream-visible output
- **WHEN** the eventless owner-side deadline would otherwise elapse
- **THEN** this watchdog does not retire the session
- **AND** existing stream, request-budget, and waiter-triggered timeout behavior remains authoritative

#### Scenario: Timeout is fail-closed and account-neutral

- **GIVEN** an eventless pre-created owner reaches the owner-side deadline
- **WHEN** terminal cleanup runs
- **THEN** every pending request is settled exactly once and the whole session is retired
- **AND** the proxy does not replay the timed-out request or submit it on another account
- **AND** the selected account is not marked unhealthy solely because `response.created` was missing
