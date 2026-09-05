## ADDED Requirements

### Requirement: Outbound connectors share one TLS verification context

Outbound HTTP connectors MUST reuse one process-wide `ssl.SSLContext` built
with the existing verification policy (`ssl.create_default_context()` plus
the certifi bundle). Sharing MUST NOT change verification mode, hostname
checking, protocol floor, socket options, or the trust store relative to a
fresh build of the same constructor. Closing the shared HTTP client MUST
drop the cached context so a later construction rebuilds it. Tests MUST be
able to rebuild the context after an explicit reset.

#### Scenario: Connectors reuse one context instance

- **WHEN** two outbound connectors are constructed in the same process
- **THEN** they receive the same verification `SSLContext` instance

#### Scenario: Shared context matches a fresh build

- **WHEN** a cached verification context is compared with a newly constructed context
- **THEN** verification mode, hostname checking, protocol floor, options, and CA store contents match
- **AND** the two objects are not the same instance

#### Scenario: Shared client shutdown rebuilds the context

- **WHEN** the shared outbound HTTP client is closed
- **THEN** the next connector construction builds a new verification context
