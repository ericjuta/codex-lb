## MODIFIED Requirements

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
