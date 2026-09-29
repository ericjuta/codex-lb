## Context

`/backend-api/files` and `/backend-api/files/{file_id}/uploaded` flow through `_FileOpsMixin._proxy_files_call`. That path selects an account, refreshes it, calls `app/core/clients/files.py`, converts `FileProxyError` to `ProxyResponseError`, and uses `ProxyService._retry_previsible_unary_call_failover`.

The failover loop excludes the failed account, respects the request deadline, and refuses to leave `strict_account_id`. Finalize sets that value from the in-memory file-account pin. The loop asks `_should_failover_previsible_unary_proxy_error` whether the failure is replay-safe.

Today, routed file calls go through `_codex_request`. It turns every exception, including typed `CodexTransportError`, into an untyped `upstream_unavailable` error with no failure phase, so routed pre-dispatch refusals never fail over. Process-network failures also lose `proxy_network_unavailable`. Direct aiohttp calls produce phase-tagged legacy errors that the predicate classifies by message markers.

The finalize client polls while upstream returns `status: retry`. A failure on a later poll is currently indistinguishable from a first-poll failure.

## Goals / Non-Goals

**Goals:**
- Carry typed routed transport provenance (phase, code, replay eligibility) from the file client to the unary failover predicate.
- Let typed provenance decide replay safety instead of sanitized message text.
- Never use transport-failure failover to replay finalization on another account after any poll returned an upstream response, for routed and direct polling.
- Preserve legacy classification for untyped errors, strict-owner fail-closed behavior, and account-neutral process-network handling.

**Non-Goals:**
- New retry loops, account-selection changes (including the existing `401` forced-refresh/reselection path), persistent file-owner pins, native egress, dashboard override plumbing, or upstream `_load_balancer/` / model-source / fast-mode code.
- Reclassifying direct aiohttp first-poll failures as typed. The direct transport keeps its legacy phase and message behavior until a poll returns.
- Changes to settlement, API-key reservations, request-log schema, or health-marking rules.

## Decisions

1. **Nullable `FileProxyError.retryable_same_contract`.** `None` means legacy/untyped. `True`/`False` means typed dispatch provenance. This is preferred over a separate boolean flag because one field avoids redundant state. `ProxyResponseError` already carries `retryable_same_contract: bool` and `failure_detail`.
2. **Map `CodexTransportError` before the generic `except Exception` in `_codex_request`.** Status stays 502. The payload is `openai_error(exc.error_code or "upstream_unavailable", str(exc))`, whose message is already credential-safe. Phase is preserved. Replay eligibility is `exc.retryable_same_contract and not exc.is_tls_verification_failure`, because aiohttp certificate errors are connector errors and would otherwise appear pre-dispatch.
3. **Service boundary stamping.** `_proxy_files_call` passes `retryable_same_contract=files_exc.retryable_same_contract is True`. It sets `failure_detail="transport_error"` only when provenance is not `None`, so status, parse, and legacy errors keep no detail.
4. **Typed-first predicate.** In `_should_failover_previsible_unary_proxy_error`, phase must still be `connect` and the code `upstream_unavailable`. When `failure_detail == "transport_error"`, `retryable_same_contract` decides. Otherwise the legacy transient-message heuristic decides. `proxy_network_unavailable` never satisfies the code check, so it stays account-neutral and non-replayable.
5. **Finalize poll progress closes transport-failure failover.** The existing `401` forced-refresh/reselection path is out of scope and unchanged.
   - Routed loop: set `poll_returned = True` immediately after `_codex_request` returns a response. Later typed `FileProxyError`s become `retryable_same_contract=False`.
   - Direct loop: set `poll_returned = True` when `session.post(...)` yields a response. A later caught aiohttp/timeout failure raises its `connect`-phase `FileProxyError` with typed `False`.
   - Before any poll returns, routed errors keep typed eligibility and direct errors keep legacy `None`, so a safe first-poll refusal can still use another eligible account.
   - Status and parse errors are not rewritten. Their phases are never failover-eligible, and they are not transport errors, so request logs remain accurate.

## Risks / Trade-offs

- [Replay after dispatch] → Negative route tests cover body-read, ambiguous request, TLS, and later-poll connect refusal for routed and direct transports.
- [Transient-looking text re-enabling replay] → Typed provenance overrides message text. Tests use endpoint IDs containing `timeout` to prove text cannot grant replay.
- [Cross-owner resource replay] → Pinned finalize keeps `strict_account_id`. Tests assert a single-account call sequence.
- [Shared predicate blast radius] → The typed branch triggers only for `failure_detail == "transport_error"`, which no other unary caller of this predicate produces. Unit coverage keeps a legacy-classification row.
- [Upstream divergence] → Upstream guarded only routed polling. This fork also guards direct polling as a deliberate addition for the same account-progress rule.
