## Context

`AccountsService._send_probe_request` (`app/modules/accounts/service.py`) builds a fixed Force Probe body and posts it through the shared `lease_http_session()` aiohttp client directly to `{upstream_base_url}/codex/responses`, pinned to one account and bypassing load-balancer scoring. The body carries `max_output_tokens=PROBE_MAX_OUTPUT_TOKENS` (`16`).

Two earlier changes define that field for `usage-refresh-policy`:

- `add-account-probe-endpoint` (ADDED probe requirement; scenario sends `max_output_tokens=1`).
- `probe-valid-token-floor` (MODIFIED the same requirement; `max_output_tokens=16`, nothing below the floor), after #1895 showed `1 → 400`, `16 → 200`.

Neither is synced into `openspec/specs/usage-refresh-policy/spec.md`, which has no probe requirement; only canonical `context.md` describes the `16` floor. Upstream #2496 reports that Codex has since rejected the parameter entirely: `16` returns HTTP 400 `Unsupported parameter: max_output_tokens`, and the same body without it returns 200. Ordinary Responses forwarding already strips the field before dispatch (`_UNSUPPORTED_UPSTREAM_FIELDS` in `app/core/openai/requests.py`); the probe's fixed body is the only path that still sends it. Upstream fixed this in `f8ffbac20` (#2496).

## Goals / Non-Goals

**Goals:**

- Send a probe body Codex accepts by omitting `max_output_tokens` entirely.
- Keep every other probe contract byte-for-byte: model, one-dot instructions/input, `stream=true`, `store=false`, bearer and `chatgpt-account-id` headers, 30s total / 10s connect timeouts, header-only (no SSE consumption) return, `probe_status_code` propagation with the `0` network sentinel, forced usage refresh, audit entry, and dashboard auth/error codes.
- Make the superseding contract explicit so the older `1`/`16` clauses cannot be synced later.
- Guard the failing product path (dashboard route) against any reintroduction of the field.

**Non-Goals:**

- Porting upstream-only probe settlement (`record_account_probe_result`, `get_proxy_service_for_app`, `force_refresh_result`, probing-health recovery streaks).
- Limit-warmup's separate `max_output_tokens=4` path or the warmup/compact-404 half of #1895.
- Editing the superseded changes, canonical spec/context, `docs/`, or `CHANGELOG.md` inside this change (canonical sync is a later task).
- A configurable cap, retry-on-400, or schema changes.

## Decisions

1. **Delete the key and the constant; add no replacement.** Any value is rejected, so a named constant has no remaining meaning. Rejected alternatives: keeping `PROBE_MAX_OUTPUT_TOKENS` unused (dead code), a `CODEX_LB_*` setting (operators cannot make an unsupported parameter valid), and passing the body through the Responses sanitizer (couples a fixed, fully internal payload to request-normalization code).
2. **No retry-without-field on 400.** Retrying doubles upstream traffic and would mask unrelated invalid-request errors; `probe_status_code` must stay the single request's verbatim status.
3. **ADDED requirement with a new name, not MODIFIED.** MODIFIED needs an existing canonical requirement; none exists. A distinct requirement name avoids colliding with the `Operators can probe an account to wake the upstream limiter` header the older changes add/modify, while its text explicitly supersedes their output-token clauses only.
4. **Regression at the route with a rejecting local upstream.** The incidental unit body-echo assertions on the output-token field are deleted rather than re-pinned. The integration test drives `POST /api/accounts/{id}/probe` through the real `_send_probe_request` and shared `lease_http_session` against a loopback aiohttp server that returns 400 when the body contains `max_output_tokens` and 200 otherwise, so pre-fix code yields `probeStatusCode: 400`. Post-probe `UsageUpdater.force_refresh` is stubbed so the loopback stub only has to serve the probe path.

## Risks / Trade-offs

- [No explicit output cap] → The fixed one-dot prompt and returning at response headers keep upstream work small; some quota may still be spent, as with any probe.
- [Upstream contract changes again] → The route regression pins the request shape and `probe_status_code` keeps upstream rejections visible to operators.
- [Older changes archived later re-sync `1`/`16`] → `context.md` records those clauses as superseded; canonical sync of this change must also remove the `16` floor text from `usage-refresh-policy/context.md`.

## Migration Plan

Code-only; no data or config migration. Deploy normally. Rollback restores the previous body (which upstream rejects with 400), so rollback only reintroduces the current failure.
