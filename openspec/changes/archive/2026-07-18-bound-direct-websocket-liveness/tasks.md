## 1. Configuration and Connection Budgeting

- [x] 1.1 Add typed settings for the direct WebSocket total connection budget and per-attempt timeout.
- [x] 1.2 Clamp the direct WebSocket connect deadline to the dedicated total budget and each upstream open to the configured per-attempt timeout.

## 2. Failover Behavior

- [x] 2.1 Replace same-account open-timeout retry with immediate request-scoped account exclusion and failover.
- [x] 2.2 Preserve file-owner, previous-response-owner, sticky-mapping, error-accounting, and terminal-settlement behavior.

## 3. Verification and Operations

- [x] 3.1 Add regression tests for settings, timeout clamping, movable failover, pinned failure, and terminal settlement.
- [x] 3.2 Run focused tests, formatting and lint checks, strict OpenSpec validation, and the repository local CI gate.
- [x] 3.3 Sync the completed delta specs and prepare the verified change for archival before deployment.
