## 1. Contract

- [x] 1.1 Define control-character handling for reconstructed and ordinary headers.
- [x] 1.2 Preserve reservation settlement and owner/file boundary semantics.

## 2. Implementation

- [x] 2.1 Reject unsafe signed bridge-forward context metadata before signing.
- [x] 2.2 Drop unsafe ordinary client and authorization headers.

## 3. Regression Coverage

- [x] 3.1 Cover unsafe client headers and permitted horizontal-tab values.
- [x] 3.2 Cover unsafe affinity and reservation metadata.
- [x] 3.3 Cover service-level rejection before the owner POST.

## 4. Validation (Fork Verification Pending Parent Execution)

- [ ] 4.1 Run unit test slices for owner forwarding and headers.
- [ ] 4.2 Run Ruff and type checks.
- [ ] 4.3 Validate OpenSpec change delta.
