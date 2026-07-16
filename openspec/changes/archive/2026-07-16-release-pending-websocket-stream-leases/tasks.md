## 1. Lease Lifecycle

- [x] 1.1 Release the current connection-owned account stream lease before adopting a pending request's lease.
- [x] 1.2 Release and clear orphaned request-owned stream leases during pending WebSocket failure cleanup.

## 2. Verification

- [x] 2.1 Add regression coverage proving pending cleanup clears the lease and decrements account stream pressure.
- [x] 2.2 Run focused tests and lint for the affected WebSocket lifecycle paths.
- [x] 2.3 Validate the OpenSpec change and all main specs strictly.
