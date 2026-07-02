## ADDED Requirements

### Requirement: WebSocket continuity state rows are pruned proactively
The system SHALL prune persisted WebSocket continuity state rows older than
48 hours as part of the existing leader-elected background cleanup loop, and
the pruning step SHALL be guarded so that its failure — including the
`websocket_continuity_states` table not existing yet mid-rollout — does not
prevent the loop's other cleanup steps from running.

#### Scenario: Cleanup loop removes stale continuity rows
- **WHEN** the cleanup loop runs and finds `websocket_continuity_states` rows
  with `updated_at` older than 48 hours
- **THEN** it deletes those rows
- **AND** rows updated within the last 48 hours survive

#### Scenario: Missing continuity table does not break the loop
- **WHEN** the cleanup loop runs before the continuity-state migration has
  been applied
- **THEN** the continuity pruning step fails quietly
- **AND** the prompt-cache and bridge-session purges in the same loop still
  run
