## 1. Contract

- [x] 1.1 Add a `responses-api-compat` delta for response-owned tool-search IDs in direct WebSocket fresh retries.

## 2. Fresh-retry preparation

- [x] 2.1 Require completed, ordered, self-contained, client-owned tool-search pairs before WebSocket fresh retry.
- [x] 2.2 Add an immutable tool-search item sanitizer that removes only replayed top-level `id` fields.
- [x] 2.3 Apply the sanitizer to client full-resend and proxy-injected-anchor retry payloads without changing anchored submissions.

## 3. Regression coverage

- [x] 3.1 Cover client-supplied and proxy-injected sanitizing retries, full-history retention, caller-input immutability, ordinary anchored behavior, and rejected server-owned, orphan, and incomplete pairs.
