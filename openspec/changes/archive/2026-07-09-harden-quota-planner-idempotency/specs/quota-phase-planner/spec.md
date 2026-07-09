## ADDED Requirements

### Requirement: Quota planner decision writes are conflict-safe

The quota planner decision repository MUST persist a decision through an atomic conflict-safe insert keyed by `idempotency_key`. For the supported PostgreSQL and SQLite databases, a colliding decision write MUST return the already persisted canonical decision without modifying its audit fields or raising an expected uniqueness failure.

#### Scenario: Concurrent scheduler ticks share an idempotency key

- **GIVEN** two planner ticks attempt to record decisions with the same `idempotency_key`
- **WHEN** both writes reach the decision repository
- **THEN** the database retains exactly one decision row for that key
- **AND** each caller receives the canonical persisted decision
- **AND** the duplicate attempt does not produce an expected unique-constraint failure

#### Scenario: Existing decision remains canonical

- **GIVEN** a decision already exists for an `idempotency_key`
- **WHEN** a later write supplies different audit values for the same key
- **THEN** the repository returns the original persisted decision
- **AND** the original decision's audit values remain unchanged