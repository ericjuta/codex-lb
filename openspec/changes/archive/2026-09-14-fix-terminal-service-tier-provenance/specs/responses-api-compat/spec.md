## MODIFIED Requirements

### Requirement: Request logs persist requested, actual, and billable service tiers separately
For Responses proxy traffic, the system MUST persist the operator-requested tier, the upstream-reported actual tier when available, and the effective billable tier used for pricing as separate request-log fields.

The legacy `fast` alias MUST be normalized to `priority` before forwarding and before it is stored as the requested tier. For streaming requests, `actual_service_tier` MUST come only from a nonblank service tier explicitly present in `response.completed.response`. Created, in-progress, failed, incomplete, cancelled, and disconnected streams MUST NOT supply actual-tier evidence. A completed response that omits the tier MUST leave actual-tier evidence absent even if earlier events supplied one. Non-streaming successful compact responses MAY supply actual-tier evidence directly.

The system MUST preserve the existing billable-tier fallback independently of actual-tier evidence. An explicit terminal tier MUST take precedence for billing; otherwise the existing observed-event/request fallback remains available without being copied into `actual_service_tier`.

Continuation reconstruction MUST preserve the final upstream terminal response's `service_tier`, including its absence. It MUST NOT inherit a tier from the initial created response when the terminal omits the field. Proxy-synthesized incomplete responses MUST NOT claim an upstream terminal tier from the created response.

#### Scenario: Upstream reports a downgraded actual tier
- **WHEN** a client sends a Responses request with `service_tier: "priority"`
- **AND** the upstream completion explicitly reports `service_tier: "default"`
- **THEN** the persisted request log records requested tier `priority`, actual tier `default`, and billable tier `default`

#### Scenario: Fast alias is logged as a priority request
- **WHEN** a client sends `service_tier: "fast"`
- **AND** the upstream completion explicitly reports `service_tier: "default"`
- **THEN** the persisted request log records requested tier `priority`, actual tier `default`, and billable tier `default`

#### Scenario: Upstream omits the actual tier
- **WHEN** a client requests `priority` and no upstream event reports a tier
- **THEN** actual tier is null and billable tier falls back to requested `priority`

#### Scenario: Initial auto does not replace terminal priority
- **WHEN** a continued response starts with created tier `auto` and finishes with explicit terminal tier `priority`
- **THEN** the folded completion and persisted actual tier are `priority`
- **AND** every upstream continuation request retains the requested tier

#### Scenario: Created-only tier remains accounting fallback
- **WHEN** a created response reports `default` and the completion omits `service_tier`
- **THEN** the completion does not inherit `service_tier`
- **AND** actual tier is null while the existing billable-tier fallback remains `default`

#### Scenario: Failed or interrupted stream does not prove a terminal tier
- **WHEN** a stream reports a created tier but fails, is cancelled, disconnects, or finishes incomplete
- **THEN** actual-tier evidence remains absent
