## 1. Implementation

- [x] 1.1 Remove the bare `credits_has = true` branch from `app/core/usage/quota.py::_has_usable_credits`, keeping unlimited credits and positive numeric balances as overrides
- [x] 1.2 Leave primary/secondary precedence, operator-disabled handling, advisory `infer_status_from_usage=False`, runtime-reset/cooldown handling, and `mappers._has_credit_override` unchanged

## 2. Regression coverage

- [x] 2.1 Extend existing account-summary mapper credit cases: a bare `credits_has` flag with missing, zero, or negative balance keeps an exhausted secondary window `quota_exceeded`; positive or unlimited credits still yield `active`; primary exhaustion and operator-disabled cases are preserved
- [x] 2.2 Extend existing proxy account-state cases: a persisted `quota_exceeded` account with a bare flag and a future runtime reset stays out of selection, positive or unlimited credits still select it, and an `ACTIVE` seed keeps its advisory behavior
- [x] 2.3 Confirm `tests/integration/test_load_balancer_multi_replica.py` has no existing credit or `quota_exceeded` section to adapt; leave it unchanged rather than add new infrastructure

## 3. Verification and closeout

- [x] 3.1 Parent settled focused verification passed 442 tests with runtime warnings treated as errors. Parent repository-wide Ruff check/format check passed; 840 files already formatted.
- [x] 3.2 Parent pure-service/integrated local smoke checked missing/zero/negative balances with a bare flag in dashboard inference and persisted-future-reset proxy modes, plus positive/unlimited overrides. Normal advisory-active and cooldown behavior was unchanged. No live upstream proof.
- [x] 3.3 `npx --yes @fission-ai/openspec validate require-spendable-credit-override --strict` passed.
- [x] 3.4 Sync the exact MODIFIED requirement into canonical `usage-refresh-policy`, preserving the original three scenarios verbatim and adding only the bounded bare-flag scenario; promote stable context and record adoption in `proxy-admission-control/ops.md`. Upstream #2078 and its second credit requirement were not imported.
- [x] 3.5 After parent review clearance, archive the completed change under the explicit authoritative 2026-09-29 path, preserving `.openspec.yaml` and without reapplying the synced delta.
