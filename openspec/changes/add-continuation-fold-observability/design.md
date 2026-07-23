## Context

The continuation fold engine has two implementations sharing one metrics
recorder: the HTTP pull fold
(`app/core/clients/codex_continuation.py::fold_responses_stream_with_codex_continuation`)
and the WebSocket push fold
(`app/modules/proxy/_service/websocket/continuation.py::_WebSocketContinuationFold`).
Both call `_record_continuation_decision(transport=..., decision=..., tier=...)`
at round terminals matching the `truncation_step * n - 2` fingerprint. Neither
path currently has access to the request's user-agent group or reasoning
effort at the point of recording. The WebSocket mixin already computes
`useragent, useragent_group = _request_log_useragent_fields(headers)` for
request logs (`app/modules/proxy/_service/support.py:254`), and the request
payload's `reasoning.effort` flows through both fold constructors inside
`base_body`.

Live tier distribution (69 samples) is dominated by tier 1 (58) with a 36%
`buffered_tool_calls` share, and a `max_continue` A/B soak is planned; both
readouts need client/effort attribution and a recovered-vs-forfeited token
signal.

## Goals / Non-Goals

**Goals:**
- One-query attribution of fold decisions by client and reasoning effort on
  both transports.
- Measurable recovered vs. forfeited vs. natural reasoning-token outcomes per
  fold terminal, sufficient to read the planned `max_continue` soak.
- Zero behavior change to fold eligibility, round construction, settlement, or
  downstream events; bounded label cardinality.

**Non-Goals:**
- No `max_continue` default change (that is the follow-up soak change).
- No client-side (nanocodex) changes.
- No request-log schema or database changes.
- No histogram of token magnitudes; counters suffice for the soak readout.

## Decisions

1. **Attribution flows through explicit parameters, not a context var.** Add
   `client_label: str` and `effort_label: str` parameters threaded into both
   fold constructors and `_record_continuation_decision`. Alternative
   considered: a request-scoped `contextvars` channel - rejected because the
   WebSocket relay multiplexes requests on one task and the fold objects
   already receive per-request state explicitly; explicit plumbing is
   testable and matches existing style.
2. **`client` label reuses `_request_log_useragent_fields` group derivation.**
   The group (first UA token before `/`) is already the request-log
   convention and is naturally low-cardinality (`nanocodex`, `codex_cli_rs`,
   etc.). Sanitize to `[a-z0-9_-]`, lowercase, max 32 chars, else `unknown`.
   Alternative: raw `client_version` query param - rejected; unbounded
   cardinality and only present on the models poll, not Responses requests.
3. **`effort` label parsed once from the visible round's request body**
   (`payload["reasoning"]["effort"]`), validated against the closed set at
   label time. Hidden continuation rounds inherit the visible round's effort;
   no re-parse per round.
4. **Token outcomes use a labeled counter, not a histogram.**
   `codex_lb_codex_continuation_reasoning_tokens_total{transport,outcome,client,effort}`
   incremented by the terminal round's
   `usage.output_tokens_details.reasoning_tokens`. Outcome classes: `recovered`
   (fold continues), `forfeited` (cap/capability stop: `max_continue`,
   `max_total_output_tokens`, `no_encrypted_content`, `missing_round_anchor`,
   `tier_out_of_window`), `natural` (`buffered_tool_calls`, `stop`). A
   histogram was rejected: the soak compares sums and rates, not
   distributions, and buckets would multiply series count against 4 labels.
5. **Labels are additive on the existing decision counter.** The counter is
   registered once at import; the label-set change ships as a code change with
   process restart, and existing dashboard queries that aggregate without the
   new labels keep working via implicit sum.
6. **Decision recording remains fail-open.** All new recording keeps the
   `PROMETHEUS_AVAILABLE` no-op guard and never raises into the fold path.

## Risks / Trade-offs

- [Label cardinality growth: client x effort x decision x tier] -> client is
  sanitized/bounded and observed values are few (2-3 groups); effort is a
  closed 7-value set; worst-case series count stays in the low hundreds.
- [WebSocket fold reconstructed on failover/replay loses attribution] -> the
  mixin re-creates `_WebSocketContinuationFold` on replay (mixin.py:1005,
  1500); pass the already-computed `useragent_group` from request state at
  both construction sites so replay keeps the same labels.
- [HTTP fold call sites lack headers today] -> `proxy.py:2751` has the request
  context in scope; thread the two label strings only, not the header map.
- [Double-counting recovered tokens across chained rounds] -> each terminal is
  recorded once per round with that round's reasoning tokens; the sum over
  `recovered` is the total carried-forward thinking, which is the intended
  semantics; document in context.md.
- [Concurrent cherry-pick lane is resolving conflicts in adjacent runtime
  files (`http_bridge/*`, `support.py`, `service.py`)] -> this change adds
  only new files under `openspec/changes/add-continuation-fold-observability/`;
  implementation edits to shared runtime files land in the apply phase and
  must be rebased against the then-current head after that lane merges. Line
  references in this design may drift.

## Migration Plan

- Pure code change; deploy via normal container rebuild/restart. New labels
  appear on first post-restart fold decision. Rollback is a revert; no data
  or schema migration. Pre-restart series with the old label set simply stop
  growing (acceptable; Grafana queries aggregate).

## Open Questions

- None blocking. Whether `stop` should count as `natural` vs its own outcome
  was resolved as `natural` (it is the model's genuine terminal).
