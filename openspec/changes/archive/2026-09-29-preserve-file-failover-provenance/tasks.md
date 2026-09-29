## 1. File client provenance

- [x] 1.1 Add optional `retryable_same_contract` (default `None`) to `FileProxyError` in `app/core/clients/files.py`
- [x] 1.2 Map `CodexTransportError` in `_codex_request` before generic exception mapping: preserve error code and failure phase, and set replay eligibility false for TLS verification failures
- [x] 1.3 Track `poll_returned` in the routed finalize loop and force typed `retryable_same_contract=False` on later typed failures
- [x] 1.4 Track `poll_returned` in the direct aiohttp finalize loop and raise later connection failures with typed `retryable_same_contract=False`; keep first-poll errors legacy

## 2. Service propagation

- [x] 2.1 Forward explicit replay eligibility from `FileProxyError` to `ProxyResponseError` in `_proxy_files_call`, and stamp `failure_detail="transport_error"` only when provenance is typed
- [x] 2.2 Make `_should_failover_previsible_unary_proxy_error` use typed provenance before the legacy message heuristic

## 3. Regression coverage

- [x] 3.1 Add route tests for routed create/finalize failover: safe first-connect fallback, TLS/ambiguous/body-read no-replay, `proxy_network_unavailable` retained, and pinned finalize fail-closed
- [x] 3.2 Add route tests where a returned retry poll followed by connection failure never uses transport-failure failover to replay finalization on another account, for routed and direct transports, plus a direct first-poll legacy failover control
- [x] 3.3 Add unit coverage for the typed-over-message predicate precedence and the legacy fallback

## 4. Verification

- [x] 4.1 Parent settled focused verification passed 442 tests with runtime warnings treated as errors. `npx --yes @fission-ai/openspec validate preserve-file-failover-provenance --strict` passed (with an informational warning about inherited duplicate requirements in the canonical target). Parent repository-wide Ruff check/format check also passed; 840 files already formatted.
- [x] 4.2 Parent real-socket local smoke: direct first refusal retained legacy `None` and eligible failover; direct retry-response then refusal became typed `False` and non-replayable; routed first refusal was typed `True` and replayable; routed retry-response then refusal was typed `False` and non-replayable. No live upstream proof.
- [x] 4.3 Sync both distinct requirements into canonical `responses-api-compat`, promote stable context, and record adoption and the deliberate direct-finalize guard beyond upstream in `proxy-admission-control/ops.md`. All original unrelated requirement blocks were retained verbatim.
- [x] 4.4 After parent review clearance, archive the completed change under the explicit authoritative 2026-09-29 path, preserving `.openspec.yaml` and without reapplying the synced delta.
