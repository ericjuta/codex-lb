## 1. Implementation

- [x] 1.1 Preserve terminal service-tier values and omission through continuation folding.
- [x] 1.2 Separate direct-stream terminal evidence from accounting fallback and gate mismatch counters on successful completion.
- [x] 1.3 Apply the same actual-tier contract to native WebSocket and HTTP bridge settlement.

## 2. Verification

- [x] 2.1 Prove conflicting, missing, and failed-terminal cases through response and request-log regressions.
- [x] 2.2 Run focused tests, required repository validation, and independent review on the settled tree.
- [ ] 2.3 Synchronize the normative specs and operational context, then validate and archive this change.

## 3. Release

- [ ] 3.1 Publish a PR targeting ericjuta/codex-lb main and satisfy current-head CI and review gates.
- [ ] 3.2 Merge and deploy the verified revision without changing runtime settings.
- [ ] 3.3 Verify deployment identity and readiness, then inspect aggregate normal-traffic terminal-tier evidence without model benchmarks or payload capture.
