# deployment-networking Specification

## Purpose

Define network exposure and policy contracts so chart deployments default to explicit, least-privilege connectivity.

## Requirements

### Requirement: NetworkPolicy ingress defaults fail closed

When the Helm chart enables `networkPolicy`, it MUST NOT open the main HTTP ingress port to every namespace by default. Namespace-scoped ingress access MUST be rendered only when an explicit allowlist selector is configured, or when the operator supplies an equivalent extra ingress rule.

#### Scenario: Empty ingress namespace selector does not create an allow-all rule

- **WHEN** `networkPolicy.enabled=true`
- **AND** `networkPolicy.ingressNSMatchLabels` is empty
- **THEN** the rendered NetworkPolicy does not include `namespaceSelector: {}`
- **AND** ingress remains deny-by-default unless the operator adds an explicit allow rule

### Requirement: Stock Docker networking supports host network changes

Stock Compose deployments MUST declare a user-defined default bridge so Docker's embedded resolver can refresh external forwarding servers after a host network change. Stock configuration MUST NOT hard-code a public recursive DNS server.

#### Scenario: Compose uses a user-defined default bridge

- **WHEN** Docker Compose renders either stock Compose deployment
- **THEN** the server is attached to a user-defined default bridge
- **AND** the rendered service does not pin a public DNS server
