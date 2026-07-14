## Tasks

- [x] Add `account_usage_percent`, `account_usage_reset_seconds` gauges and `account_transient_errors_total` counter to the metrics registry (real + fallback declarations, `__all__`).
- [x] Set usage gauges from the usage refresh scheduler after each successful refresh cycle.
- [x] Increment the transient error counter where transient account errors are recorded.
- [x] Unit tests: gauges reflect latest usage rows; counter increments with the normalized code label.
- [ ] Validate specs (`openspec validate --specs`), run focused tests, deploy, verify.
