# Tasks

## 1. Contract

- [x] 1.1 Specify hard turn-state and previous-response continuity on a canonical prompt-cache bridge.
- [x] 1.2 Preserve prompt-cache-only soft locality, recovery exceptions, and file-owner separation.

## 2. Implementation

- [x] 2.1 Route a live remote canonical prompt-cache owner through authenticated owner forwarding.
- [x] 2.2 Leave no local inflight creation reservation after owner forwarding.

## 3. Regression Coverage

- [x] 3.1 Add a focused service regression for the retained canonical prompt-cache key.
- [x] 3.2 Add `/v1/responses` coverage for the two-replica continuation path.

## 4. Validation (Fork Verification Pending Parent Execution)

- [ ] 4.1 Run focused unit and integration tests.
- [ ] 4.2 Run Ruff and type checks.
- [ ] 4.3 Validate OpenSpec change delta.
