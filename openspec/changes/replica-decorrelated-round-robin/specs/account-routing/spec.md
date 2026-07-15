# account-routing Specification

## ADDED Requirements

### Requirement: Round-robin tie-breaking is decorrelated across replicas

The `round_robin` routing strategy SHALL order candidate accounts primarily by
planner cost and then by least-recently-selected time, and SHALL break any
remaining exact tie using a per-replica salt mixed into the account identifier
through a keyed hash. The salt SHALL be stable for the lifetime of a replica
process (not randomized per selection). A bridge-enabled runtime SHALL use its
configured HTTP responses-session bridge instance identity unchanged. When no
unique bridge worker identity is available, including bridge-disabled
multi-worker Uvicorn, the fallback SHALL combine host identity with a stable
process-specific component and SHALL recompute after a process fork. Mixing the
salt SHALL change only the final tie-break: the planner-cost and
least-recently-selected ordering SHALL remain identical to selection without a
salt, so only genuinely tied candidates are reordered.

#### Scenario: Replicas with distinct salts spread an exact tie

- **GIVEN** two or more healthy eligible accounts that are exactly tied on
  planner cost and least-recently-selected time
- **AND** two replicas configured with distinct per-replica salts
- **WHEN** each replica selects with the `round_robin` strategy
- **THEN** the replicas MAY break the tie toward different accounts so load
  spreads across the equally-good candidates instead of herding onto one

#### Scenario: Primary ordering is unaffected by the salt

- **GIVEN** candidate accounts that differ in planner cost or
  least-recently-selected time
- **WHEN** account selection uses the `round_robin` strategy under any salt
- **THEN** the account with the lower planner cost, or when costs are equal the
  least-recently-selected account, is selected regardless of the salt value

#### Scenario: Single-replica selection is deterministic

- **GIVEN** a fixed set of candidate accounts and a fixed per-replica salt
- **WHEN** the `round_robin` strategy selects repeatedly with unchanged state
- **THEN** the same account is selected every time

#### Scenario: Bridge worker identity is preserved

- **GIVEN** bridge-enabled workers with distinct configured instance identities
- **WHEN** each worker initializes its round-robin replica salt
- **THEN** each configured bridge instance identity is used unchanged

#### Scenario: Bridge-disabled sibling workers are decorrelated

- **GIVEN** two bridge-disabled Uvicorn workers on the same host
- **WHEN** each process initializes its fallback replica salt
- **THEN** each salt is stable within its worker
- **AND** the salts differ by a process-specific component
- **AND** a value cached before a process fork is recomputed in the child
