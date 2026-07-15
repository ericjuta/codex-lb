## 1. Chronology correction

- [x] 1.1 Compare local fresh-usage recovery evidence with the precise runtime block timestamp.
- [x] 1.2 Add deterministic subsecond coverage proving pre-block same-second usage cannot reactivate the account.

## 2. Validation

- [x] 2.1 Run the focused load-balancer unit regression and existing sticky-session integration test in serial and xdist modes.
- [x] 2.2 Run focused Ruff and ty checks, strict OpenSpec validation, and final diff/status review.

## 3. Serving and status parity

- [x] 3.1 Publish direct Responses WebSocket rate-limit frames through the existing live-usage hub.
- [x] 3.2 Gate account-summary rate-limit recovery on routing-equivalent post-block usage evidence.
- [x] 3.3 Add direct relay and `/api/accounts` product-path regressions.
- [x] 3.4 Preserve the precise runtime block marker across repeated selection-state synchronization.

## 4. Expanded validation

- [x] 4.1 Run the direct relay and account API regressions with the chronology regression.
- [x] 4.2 Re-run focused Ruff, ty, strict OpenSpec validation, and final diff/status review.
