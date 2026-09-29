## 1. Implementation

- [x] 1.1 Trim and validate supplied quota planner timezones with `ZoneInfo` before settings persistence; keep blank or missing input as the current value.
- [x] 1.2 Extend `_to_planner_tz` UTC fallback to malformed timezone keys (`ValueError`).

## 2. Regression coverage

- [x] 2.1 API tests: invalid names and malformed keys return HTTP 400 `invalid_quota_planner` without persisting any supplied setting.
- [x] 2.2 API tests: trimmed valid timezone persists; omitted, null, empty, and whitespace timezone retain the current (including legacy) value while other settings save.
- [x] 2.3 API and unit tests: legacy malformed stored timezones produce forecasts and routing costs equal to UTC instead of raising.

## 3. Verification

- [x] 3.1 Exercise `tests/integration/test_quota_planner_api.py` and `tests/unit/test_quota_planner.py` in the parent settled focused verification (442 tests total, runtime warnings treated as errors).
- [x] 3.2 Parent repository-wide `uv run --frozen ruff check` and `uv run --frozen ruff format --check` exited 0; 840 files already formatted.
- [x] 3.3 `npx --yes @fission-ai/openspec validate validate-quota-planner-timezones --strict` passed.
- [x] 3.4 Parent standalone real-settings-API smoke: three malformed/unknown timezone variants returned 400 without persistence; valid normalization and blank retention worked. Legacy malformed stored values in forecasts and routing costs were verified by the full planner regression modules in 3.1, not a separate standalone foreground proxy-selection smoke.

## 4. Canonical closeout

- [x] 4.1 Sync both distinct ADDED requirements and stable narrative context into canonical `quota-phase-planner`, preserving all original requirement blocks; record the adopted SHA and boundaries in `proxy-admission-control/ops.md`.
- [x] 4.2 After parent review clearance, archive the completed change under the explicit authoritative 2026-09-29 path, preserving `.openspec.yaml` and without reapplying the synced delta.
