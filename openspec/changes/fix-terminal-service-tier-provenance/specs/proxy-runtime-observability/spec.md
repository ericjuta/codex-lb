## ADDED Requirements

### Requirement: Service-tier mismatches use successful terminal evidence
The service-tier mismatch counter MUST count only successful requests with an explicit nonblank terminal-reported tier that differs from the normalized requested tier. A created or in-progress tier, requested-tier fallback, missing terminal tier, or unsuccessful attempt MUST NOT increment the counter. The change MUST preserve existing counter coverage and bounded labels rather than adding identities or payload data.

An explicitly returned `auto` MUST remain observable as the reported tier. Operator guidance MUST describe it as inconclusive for Fast delivery rather than proof of a downgrade. Counter equality or absence MUST NOT be described as evidence of upstream scheduling.

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
