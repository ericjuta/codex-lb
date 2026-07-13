# Delta: sticky-session-operations

## ADDED Requirements

### Requirement: Per-request account exclusion preserves sticky mappings

When account selection resolves an existing sticky mapping whose pinned account is absent from the candidate pool solely because it was excluded for the current request (for example transport failover after a connect failure), the system MUST select a fallback account for that request without deleting or rewriting the sticky mapping, for every sticky-session kind. Sticky mappings SHALL only be deleted or rebound by pool-membership changes (account removed or out of scope), permanent account status, budget-pressure reallocation, TTL expiry, or explicit administrative action.

#### Scenario: Transport failover keeps the prompt-cache mapping

- **GIVEN** a `prompt_cache` mapping pinned to account A
- **WHEN** a request excludes account A after a transient connect failure and selection reallocates
- **THEN** a fallback account serves the request
- **AND** the `prompt_cache` mapping still points at account A
- **AND** a subsequent request without the exclusion returns to account A

#### Scenario: Transport failover keeps the durable codex-session mapping

- **GIVEN** a `codex_session` mapping pinned to account A
- **WHEN** a request excludes account A after a transient connect failure and selection reallocates
- **THEN** a fallback account serves the request
- **AND** the `codex_session` mapping still points at account A

#### Scenario: Pinned account removed from the pool still deletes the mapping

- **GIVEN** a sticky mapping pinned to an account that has been deleted or moved out of the API-key scope
- **WHEN** selection resolves the mapping and the account is not in the candidate pool for a non-exclusion reason
- **THEN** the stale mapping is deleted and the fallback placement is persisted

### Requirement: Sticky selection outcomes are observable

The system MUST record a sticky-selection outcome metric (`codex_lb_sticky_selection_total`) labeled by sticky kind and outcome for every selection that carries a sticky key, with outcomes distinguishing at least: pinned account selected (`hit`), fallback without mapping mutation (`fallback`), fallback persisted over an existing mapping (`rebind`), and first placement (`new`). The metric MUST be a no-op when the metrics backend is unavailable.

#### Scenario: Pinned selection increments hit

- **WHEN** selection returns the account already stored in the sticky mapping
- **THEN** the counter increments with outcome `hit` and the mapping's kind label

#### Scenario: Preserved fallback increments fallback

- **WHEN** selection returns a different account while preserving the existing mapping
- **THEN** the counter increments with outcome `fallback`

#### Scenario: Persisted rebind increments rebind

- **WHEN** selection persists a fallback account over an existing mapping
- **THEN** the counter increments with outcome `rebind`

#### Scenario: First placement increments new

- **WHEN** selection creates a sticky mapping where none existed
- **THEN** the counter increments with outcome `new`
