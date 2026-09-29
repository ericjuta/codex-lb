# File failover provenance: context

Normative requirements live in `specs/responses-api-compat/spec.md` in this change. This file records purpose, decisions, constraints, failure modes, and an example.

## Purpose and scope

This port brings upstream `6b10052ec` (#2469) to routed and direct file create/finalize calls. Account failover should follow what the transport proved about dispatch, not a sanitized error string.

File ownership stays in this fork's in-memory TTL pin table (`_pin_file_account`, `_resolve_file_account`). Not adopted from upstream: `FileAccountPinRepository`, native egress discovery, `with_dashboard_overrides`, `_load_balancer/` decomposition, model sources, and fast-mode policy.

## Decisions

- `FileProxyError.retryable_same_contract` is tri-state:
  - `None`: legacy/untyped, such as direct aiohttp errors before any poll response.
  - `True`: typed and replay-safe.
  - `False`: typed and not replay-safe.
- `_proxy_files_call` sets `failure_detail="transport_error"` only for typed errors. The shared predicate uses the typed flag only for that detail, so other unary callers keep their current classification.
- TLS verification failures are masked to non-replayable. aiohttp certificate errors subclass connector errors, which would otherwise mark them pre-dispatch.
- The finalize-poll guard covers both routed and direct loops. Upstream guarded only routed polling; this fork applies the same account-progress rule to direct polling. The guard closes only transport-failure failover eligibility; the existing `401` forced-refresh and account-reselection path is unchanged.

## Constraints and failure modes

- A finalize operation that received `status: retry` from account A has made upstream progress on A. Even if a later poll fails before dispatch, transport failover to B could finalize or misreport a file B does not own. This change does not alter the separate `401` re-authentication/reselection path; pinned finalize ownership remains enforced.
- `proxy_network_unavailable` stays account-neutral: it does not penalize account health and does not replay across accounts.
- Pinned finalize always fails closed on the owner, before or after any poll response.
- Status and parse errors are not stamped as transport errors. Their phases are never failover-eligible, and request logs keep an accurate `failure_detail`.

## Example

An unpinned file finalize selects account A through proxy endpoint `timeout-a`.

- **Retry, then refusal:** The first poll returns `{"status":"retry"}`, then the second poll's proxy CONNECT is refused. The error text `Codex upstream request failed via proxy endpoint timeout-a: ClientProxyConnectionError` looks transient. Typed provenance is `False`, so the client receives 502 `upstream_unavailable`, and A made both polls.
- **Immediate refusal:** If the first poll's CONNECT is refused before any poll returns, the typed flag is `True`. The request then completes on eligible account B.
