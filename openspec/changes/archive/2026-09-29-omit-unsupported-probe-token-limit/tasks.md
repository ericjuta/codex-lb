## 1. Implementation

- [x] 1.1 In `app/modules/accounts/service.py`, delete `PROBE_MAX_OUTPUT_TOKENS` and its comment, and drop the `"max_output_tokens"` key from the `_send_probe_request` body. Keep model, one-dot `instructions`/`input`, `stream=True`, `store=False`, headers, `ClientTimeout(total=PROBE_REQUEST_TIMEOUT_SECONDS, sock_connect=PROBE_CONNECT_TIMEOUT_SECONDS)`, header-only return, and the `PROBE_NETWORK_FAILURE_STATUS` path unchanged. Do not import upstream-only helpers (`record_account_probe_result`, `get_proxy_service_for_app`, `force_refresh_result`).
- [x] 1.2 Confirm no remaining references: `PROBE_MAX_OUTPUT_TOKENS` only appears at the removed declaration/body key and `tests/unit/test_accounts_service_probe.py` (import line 16, assertion line 291).

## 2. Regression coverage

- [x] 2.1 In `tests/unit/test_accounts_service_probe.py::test_send_probe_request_uses_shared_http_client`, remove the `PROBE_MAX_OUTPUT_TOKENS` import and delete both `max_output_tokens` equality assertions without a replacement body assertion. Keep URL, Authorization, `chatgpt-account-id`, model, `stream`, `store`, and timeout (`total == 30.0`, `connect is None`, `sock_connect == 10.0`) assertions.
- [x] 2.2 Add `tests/integration/test_accounts_api_probe.py::test_force_probe_omits_unsupported_max_output_tokens_upstream_accepts`: start a loopback `aiohttp.web.AppRunner`/`TCPSite` on `127.0.0.1:0` serving `POST /backend-api/codex/responses` that returns `400` `{"error":{"code":"unsupported_parameter"}}` when the JSON body contains `max_output_tokens` and `200` `text/event-stream` otherwise; point `CODEX_LB_UPSTREAM_BASE_URL` at `http://127.0.0.1:<port>/backend-api` via `monkeypatch.setenv` plus `get_settings.cache_clear()` (restore and `runner.cleanup()` in `finally`); stub `UsageUpdater.force_refresh` to return `False`; use the real `_send_probe_request` and shared `lease_http_session`; import an account, POST `/api/accounts/{id}/probe`, and assert HTTP `200` and `probeStatusCode == 200`.
- [x] 2.3 Standalone parent red/green smoke against a rejecting loopback upstream: fault-inject the old HEAD probe method in memory (`SMOKE_LEGACY_PROBE=1`), then use the fixed current method (`SMOKE_LEGACY_PROBE=0`). Both runs exited 0; the real API route returned HTTP 200 in each, with `probeStatusCode` 400 before and 200 after, and exactly one upstream request per run. The old body contained `max_output_tokens`; the fixed body did not. The originally planned pre-landing execution of the permanent 2.2 test node was not performed; this is the actual standalone behavioral proof, not alternate-worktree or live-upstream proof.

## 3. Verification

- [x] 3.1 Exercise `tests/integration/test_accounts_api_probe.py::test_force_probe_omits_unsupported_max_output_tokens_upstream_accepts` as part of the parent settled focused suite (not a separate node-only run).
- [x] 3.2 Exercise `tests/unit/test_accounts_service_probe.py` and `tests/integration/test_accounts_api_probe.py` as part of the parent settled 442-test focused verification, with runtime warnings treated as errors.
- [x] 3.3 Parent repository-wide `uv run --frozen ruff check` exited 0, "All checks passed"; `uv run --frozen ruff format --check` exited 0, 840 files already formatted.
- [x] 3.4 `npx --yes @fission-ai/openspec validate omit-unsupported-probe-token-limit --strict` passed. Canonical `validate --specs --strict` was run: 25 passed / 14 inherited failures, not a green full-spec gate. See the canonical ops ledger for the existing Purpose/duplicate-requirement failures.

## 4. Spec sync (parent-owned, outside this change directory)

- [x] 4.1 Add the ADDED requirement to `openspec/specs/usage-refresh-policy/spec.md`, replace the old floor and unsupported replica-health paragraph with the actual omission/forced-refresh rationale, promote stable context, and record adoption in `proxy-admission-control/ops.md`. The historical `1`/`16` deltas were archived without spec sync; neither was imported.
- [x] 4.2 After parent review clearance, archive the completed change under the explicit authoritative 2026-09-29 path, preserving `.openspec.yaml` and without reapplying the synced delta.
