## ADDED Requirements

### Requirement: Device OAuth replacement preserves polling cancellation

Starting a replacement device OAuth flow SHALL cancel any previous pending device poll. Cancellation during route-resolution database cleanup MUST remain effective after cleanup completes, before the previous poll starts token exchange. The replacement flow MUST remain available for polling.

#### Scenario: Replace a poll waiting for token exchange

- **WHEN** a replacement device flow starts while the previous pending flow waits for token exchange
- **THEN** the previous poll terminates through cancellation
- **AND** the replacement is the only pending device flow and continues polling

#### Scenario: Replace a poll during route-session rollback

- **WHEN** a replacement device flow starts while the previous poll rolls back its route-resolution database session
- **THEN** that cleanup finishes and the previous poll terminates through cancellation without starting token exchange
- **AND** the replacement flow continues polling

#### Scenario: Replace a poll during route-session close

- **WHEN** a replacement device flow starts while the previous poll closes its route-resolution database session
- **THEN** that cleanup finishes and the previous poll terminates through cancellation without starting token exchange
- **AND** the replacement flow continues polling
