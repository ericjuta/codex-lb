## MODIFIED Requirements

### Requirement: HTTP bridge startup admission waits are bounded

The proxy MUST apply the configured proxy admission wait timeout to each HTTP
bridge startup wait attempt for per-session response-create gate acquisition,
bridge capacity waiters, and in-flight session creation waiters.

For per-session response-create gate acquisition by a bridged Responses
request, an expired gate acquisition attempt MUST be treated as a recoverable
capacity wait rather than a terminal failure: the request MUST release its
queue slot and account lease, wait with capacity-wait progress semantics, and
retry gate acquisition, bounded by the original bridge request budget.
Requests eligible for soft-affinity reroute MUST still attempt the reroute
before entering the recoverable wait. When the original bridge request budget
is exhausted before the gate opens, the proxy MUST reject the request locally
with HTTP 429, `error.code = "response_create_gate_timeout"`, and the stable
local-overload reason.

For bridge capacity waiters and in-flight session creation waiters, when the
timeout expires the proxy MUST reject the request locally with HTTP 429 and an
OpenAI-style `proxy_overloaded` error envelope. Timing out while observing
another request's pending in-flight session creation MUST evict that in-flight
marker when it is still pending so later requests can attempt a fresh bridge
session instead of waiting on the same stalled future.

If a request owns in-flight bridge session creation and is cancelled or fails
after publishing the in-flight marker but before registering the created
session, the proxy MUST remove or settle that in-flight marker. If a session
owner later finishes creation after its in-flight marker was evicted, the owner
MUST NOT return an unregistered bridge session to the caller.

#### Scenario: Gate contention queues within the bridge request budget

- **GIVEN** an HTTP bridge session whose response-create gate is held by a legitimate in-flight turn
- **AND** a bridged Responses request that cannot soft-reroute
- **WHEN** a gate acquisition attempt exceeds the configured proxy admission wait timeout
- **THEN** the request emits capacity-wait progress and retries gate acquisition
- **AND** the request completes once the in-flight turn releases the gate before the original bridge request budget expires

#### Scenario: Gate contention still fails once the request budget is exhausted

- **WHEN** a bridged request retries gate acquisition until the original bridge request budget is exhausted
- **THEN** the request is rejected locally with HTTP 429
- **AND** the error payload uses `error.code = "response_create_gate_timeout"`
- **AND** no response-create gate lease is recorded on that request state

#### Scenario: Soft-affinity requests reroute before waiting

- **GIVEN** a soft-affinity bridge key and no `previous_response_id`
- **WHEN** the preferred session's first gate acquisition attempt times out
- **THEN** the proxy attempts a safe fresh-session reroute before entering the recoverable wait

#### Scenario: Stuck sessions are still detected between attempts

- **WHEN** a gate attempt times out after the session exceeds the stuck-gate threshold
- **THEN** the stuck-session retirement check still runs
- **AND** a retired or closed session is not retried

#### Scenario: Sleeping gate waiters remain queue-bounded

- **WHEN** a gate-contended request sleeps before another acquisition attempt
- **THEN** it occupies a bridge queue slot during the sleep
- **AND** excess waiters fail with `bridge_queue_full`

#### Scenario: In-flight bridge session creation does not finish

- **WHEN** a bridged request waits on another request's in-flight session creation
- **AND** the creation does not finish before the configured admission timeout
- **THEN** the waiter is rejected locally with HTTP 429 and `proxy_overloaded`
- **AND** the stalled marker is evicted if it is still pending

#### Scenario: Bridge capacity waiter does not make progress

- **WHEN** the bridge is at capacity and no work completes before the admission timeout
- **THEN** the waiter is rejected locally with HTTP 429 and `proxy_overloaded`

#### Scenario: In-flight owner is cancelled during stale session close

- **WHEN** a session-creation owner is cancelled after publishing its in-flight marker
- **THEN** the marker is removed or settled
- **AND** later requests do not remain blocked on its future

### Requirement: Local overload reasons are stable and distinguishable

Local Responses overload failures MUST expose stable low-cardinality reason
fields in logs and metrics so operators can distinguish
`bridge_queue_full`, `response_create_gate_timeout`,
`hard_affinity_saturated`, `previous_response_owner_unavailable`,
`global_admission_timeout`, `capacity_exhausted_active_sessions`,
`account_response_create_cap`, and `account_stream_cap`. These local
reasons MUST NOT be reported as upstream rate limits.

#### Scenario: Bridge queue saturation is not ambiguous

- **WHEN** a local HTTP bridge queue rejects a request
- **THEN** logs and metrics use the stable reason `bridge_queue_full`
- **AND** they do not use the ambiguous alias `queue_full`

#### Scenario: Queued bridge requests wait within the original request budget

- **WHEN** a visible bridge request has claimed a queue slot and its session gate is held
- **THEN** each acquisition attempt is bounded by the admission timeout
- **AND** expired attempts enter a recoverable wait bounded by the original request budget
- **AND** `response_create_gate_timeout` remains the stable terminal reason
- **AND** `bridge_queue_full` remains the queue-saturation reason

#### Scenario: Account cap rejection is local overload

- **WHEN** every eligible account is unavailable because of account-local caps
- **THEN** the response is a local overload response with `Retry-After`
- **AND** diagnostics identify `account_response_create_cap` or `account_stream_cap`
