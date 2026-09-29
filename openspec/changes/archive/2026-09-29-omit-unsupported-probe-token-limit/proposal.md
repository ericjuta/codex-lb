## Why

Dashboard Force Probe sends a fixed direct `responses.create` body containing `max_output_tokens`. The Codex Responses endpoint now rejects that field at any value (per upstream #2496, `max_output_tokens=16` returned HTTP 400 `Unsupported parameter: max_output_tokens`; the same body without the field returned HTTP 200), so a usable account reports `probeStatusCode: 400` and the probe cannot wake the upstream limiter. This ports upstream fix `f8ffbac20` (#2496) narrowly onto the local probe implementation.

## What Changes

- Omit `max_output_tokens` entirely from the direct account probe body and remove the `PROBE_MAX_OUTPUT_TOKENS` constant; no replacement cap, retry, sanitizer, or setting is introduced.
- Keep every other probe contract as it is today: model (request or `DEFAULT_PROBE_MODEL`), the one-dot `instructions`/`input`, `stream=true`, `store=false`, bearer and `chatgpt-account-id` headers, `PROBE_REQUEST_TIMEOUT_SECONDS`/`PROBE_CONNECT_TIMEOUT_SECONDS` bounds, returning after response headers without consuming SSE, `probe_status_code` propagation (upstream status, `0` on network failure), the post-probe forced usage refresh, and dashboard auth/error codes.
- **Supersedes** two earlier probe-token contracts in `usage-refresh-policy`:
  - `add-account-probe-endpoint`: the scenario clause requiring `max_output_tokens=1`.
  - `probe-valid-token-floor`: the requirement and scenario clauses requiring `max_output_tokens=16` and forbidding values below that floor.
  Only the output-token clauses are superseded; their endpoint, eligibility, snapshot, and dashboard contracts are unaffected. Those change directories, canonical spec/context, docs, and changelog are not edited by this change.
- Add route-level regression coverage whose local upstream stub rejects `max_output_tokens` (as upstream Codex does), and delete the incidental unit output-token body assertions.

Upstream helpers used by `f8ffbac20` tests (`record_account_probe_result`, `get_proxy_service_for_app`, `force_refresh_result`) do not exist locally and are not ported.

## Capabilities

### New Capabilities

- None

### Modified Capabilities

- `usage-refresh-policy`: ADDS a Force Probe request-body requirement forbidding the unsupported `max_output_tokens` field. It is ADDED rather than MODIFIED because the canonical `openspec/specs/usage-refresh-policy/spec.md` has no probe requirement; the earlier `max_output_tokens=1` and `=16` clauses live only in the earlier changes it supersedes, whose history is recorded in `context.md`.

## Impact

- `app/modules/accounts/service.py`: `PROBE_MAX_OUTPUT_TOKENS` removed; `_send_probe_request` body drops the key.
- `tests/unit/test_accounts_service_probe.py`: constant import and incidental output-token body assertions removed.
- `tests/integration/test_accounts_api_probe.py`: new rejecting-upstream Force Probe regression.
- API/dashboard: same `POST /api/accounts/{account_id}/probe` endpoint, request, response schema, and audit entry; a usable account now reports its real 2xx upstream status instead of a guaranteed 400.
- No data, migration, routing, dependency, or limit-warmup (`max_output_tokens=4` path) change.
