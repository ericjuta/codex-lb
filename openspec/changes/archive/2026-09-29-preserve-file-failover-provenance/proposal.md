## Why

Routed file create/finalize calls wrap `CodexTransportError` in `FileProxyError`, which drops failure phase, process-network code, and replay eligibility. Confirmed pre-dispatch proxy connection failures therefore cannot use existing previsible unary account failover. The service still classifies file errors from sanitized message text. File finalization can also use transport-failure failover to restart on a different account after an earlier poll already returned an upstream response.

This is a narrow fork port of upstream `6b10052ec` (Soju06/codex-lb #2469).

## What Changes

- `FileProxyError` carries optional `retryable_same_contract`. `None` marks legacy errors without typed transport provenance.
- The routed file adapter maps `CodexTransportError` before generic exception mapping. It preserves `error_code`, `failure_phase`, and replay eligibility. TLS verification failures are never replay-eligible.
- The file service boundary forwards replay eligibility to `ProxyResponseError`. It sets `failure_detail="transport_error"` only when typed provenance exists.
- The shared unary failover predicate uses typed provenance before sanitized message text. Legacy transport errors keep message classification.
- Once any finalize poll returns an upstream response, later file-finalize transport failures are not eligible for transport-failure account failover. This applies to both routed `CodexClient` polling and direct aiohttp polling. Safe first-poll connect failover is preserved. The existing `401` forced-refresh and account-reselection path is unchanged.
- Not adopted from upstream: persistent file-account pin repository, native egress discovery, `with_dashboard_overrides`, `_load_balancer/` decomposition, model sources, and fast-mode policy. File ownership remains this fork's in-memory `_pin_file_account` / `_resolve_file_account` table.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `responses-api-compat`: File operation account failover depends on typed transport provenance and finalize-poll progress.

## Impact

- Code: `app/core/clients/files.py`, `app/modules/proxy/_service/file_ops.py`, and `app/modules/proxy/service.py` (`_should_failover_previsible_unary_proxy_error`).
- The shared unary predicate is also used by Codex thread-goal, Codex control, and transcription failover. The typed branch applies only to errors stamped with `failure_detail="transport_error"`. Those callers do not produce that stamp, so their legacy classification is unchanged.
- Tests: `tests/integration/test_proxy_files.py` (public file routes) and `tests/unit/test_unary_transport_failover.py` (shared predicate precedence).
- No API, schema, migration, dependency, or dashboard change. Request logs for typed file transport failures now record `failure_detail=transport_error`.
