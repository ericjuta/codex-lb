# audit-logging Specification

## Purpose

Guarantee asynchronous audit-log writes stay owned to completion and drain during graceful shutdown.
## Requirements
### Requirement: Asynchronous audit writes remain owned until completion

The system MUST execute `AuditService.log_async()` writes in tracked background tasks without making the calling request wait for database persistence. Each task MUST remain strongly owned until it finishes, and success, cancellation, or failure MUST remove it from the tracked set. An unexpected task failure MUST be consumed and reported rather than becoming an unobserved task exception.

#### Scenario: Audit logging remains fire-and-forget

- **GIVEN** an audit-log database write is blocked
- **WHEN** application code calls `AuditService.log_async()`
- **THEN** the call returns before the database write completes
- **AND** the pending write remains tracked until completion

#### Scenario: Failed audit task is cleaned up

- **WHEN** an asynchronous audit task fails unexpectedly
- **THEN** the failure is reported
- **AND** the completed task is removed from the tracked set

### Requirement: Graceful shutdown closes asynchronous audit-task admission

Graceful shutdown MUST synchronously close asynchronous audit-task admission immediately after the in-flight drain attempt returns, before any further shutdown await. Later `AuditService.log_async()` calls MUST remain non-blocking, report the rejected action, and create no write coroutine or task.

#### Scenario: Late audit producer is rejected after in-flight timeout

- **GIVEN** an HTTP handler remains alive after the in-flight drain timeout
- **AND** graceful shutdown has closed control-plane task admission
- **WHEN** the handler calls `AuditService.log_async()`
- **THEN** the call returns without waiting
- **AND** the rejected action is reported
- **AND** no audit write coroutine or task is created

### Requirement: Graceful shutdown drains pending audit writes

Before closing shared database resources, graceful shutdown MUST wait up to `shutdown_drain_timeout_seconds` for audit tasks accepted before the admission cutoff. The drain MUST include tasks completing or becoming visible during task-completion callbacks. On timeout, it MUST report each undrained audit task before continuing shutdown.

#### Scenario: Shutdown preserves a pending audit row

- **GIVEN** an asynchronous audit write is still pending when graceful shutdown begins
- **WHEN** the write completes within the configured drain timeout
- **THEN** shutdown waits for the write
- **AND** shared database resources remain open until the write finishes

#### Scenario: Overdue audit write is reported

- **GIVEN** an asynchronous audit write remains pending for the full configured drain timeout
- **WHEN** graceful shutdown drains audit tasks
- **THEN** the drain reports that task as overdue
- **AND** shutdown is allowed to continue
