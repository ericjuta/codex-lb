# proxy-admission-control Ops Notes

## 2026-07-22 upstream pick batch: soak checkpoints and revert candidates

Nine upstream commits landed and deployed as build `a34ea3c1` (2026-07-22
12:12 UTC), archived changes `2026-07-22-*`. Two picks change behavior on the
hottest admission/keepalive path and are the designated revert candidates if
session behavior degrades:

- `#1266` (`bridge-gate-capacity-wait`, commit `5fb14a3d`): bridged
  same-session requests now queue through response-create gate contention with
  capacity-wait keepalives instead of failing 429 `local overload` at the 10s
  admission timeout. Symptom if wrong: sessions hang in capacity-wait instead
  of failing fast; look for stacked `response_create_gate` waiters.
- `#1439` (`recover-codex-desktop-idle-bridge`, commit `1e134a9d`): eventless
  bridge owners are retired via `missing_response_created_timeout` (240s) and
  native Codex clients keep codex keepalive framing on the compat route.
  Symptom if wrong: premature owner retirement mid-turn; look for
  `failure_detail_override=missing_response_created_timeout` on requests that
  were still healthy.

Both revert cleanly with `git revert` (plus the paired weave-repair hunks in
`fix(lint)`/`fix(tests)` commits `3bf46fc8..a34ea3c1`).

### Soak checks

- Log scan: `docker logs --since 24h codex-lb-direct | grep -ciE
  'response_create_gate_timeout|capacity_wait|eventless|missing_response_created'`.
  At +25 min post-deploy all counts were 0 (paths only fire under contention);
  only pre-existing `continuity_fail_closed` recovery warnings present.
- Cache/burn baseline for the `#1344` image-slimming claim (from
  `scripts/burn_report.sh` split on the deploy timestamp): pre-deploy
  `gpt-5.6-sol` cache 94.0% / 7224 uncached-per-req over 10487 reqs; first
  post-deploy sample 97.1% / 3202 over 543 reqs. Early and confounded by mix;
  re-run after ~24h before crediting the pick.

### Not picked (do not retry as cherry-picks)

`#1283`, `#1325`, `#1358`, `#1376`, `#1382` all assume upstream's
`_load_balancer/` decomposition or multi-replica invalidation namespaces this
fork does not carry. They only become viable after a deliberate wholesale
adoption of that decomposition.

## 2026-07-23 upstream pick batch

Six upstream commits picked onto the fork (see `git log`): `#1400`, `#1399`,
`#1398`, `#1451`, `#1438`, `#1447`. Fork adaptations during the weave:

- `#1438`: fork lacks the fast-mode plumbing (`prohibit_fast_mode`) and the
  model-sources lane; `apply_enforced_service_tier_model_fallback` was wired
  into the fork's four `apply_api_key_enforcement` call sites in `api.py`
  (with owner-forward tier retention in `_stream_responses`) plus the
  websocket prepare path. Upstream's source-routed control test was dropped.
- `#1447`: fork has no codex image-edit alias routes or model-source audio
  routing; kept bounded-multipart parsing, the new `app/core/multipart*.py`
  and middleware, and the OpenAPI extras block; dropped
  `_source_audio_transcription_response` and
  `tests/integration/test_model_source_routing.py`.
- `#1451`: fork was missing `openspec/specs/automations/spec.md`; adopted
  upstream's spec file wholesale.

### Not picked (adds to the July 22 list)

- `#1437` (`recover verified responses after owner loss`): aborted. The pick
  assumes upstream's decomposed `select_account` signature
  (`required_account_id` / `required_continuity_owner` /
  `sticky_source` plumbing), `effective_continuity_owner_candidates` on
  `_SelectionInputs`, and the `test_load_balancer_contract.py` /
  `test_bridge_ring_lifecycle.py` suites the fork does not carry. 15 conflicted
  files including a 500-line `select_account` weave. Viable only after a
  deliberate wholesale adoption of upstream's load-balancer decomposition,
  same as the `#1283`/`#1325` family.

## 2026-09-05 upstream bug/security batch: adoption and skips

Canonical specs describe 19 selected main-branch runtime ports and the
WebSocket fresh-replay repair from a fetched non-main branch, starting at
`fix/upstream-2026-09-05` baseline `3aabf89f`. Local verification is recorded
below; it does not establish CI or production behavior. Upstream OpenSpec
tasks/context that mention completed validation or production measurements
remain upstream provenance only.

### Adopted runtime SHAs (19)

- Observability and credentials: `fed54730` (bounded request metric labels),
  `8d02c824` (line-scoped secret redaction), `9c188de2` (aiohttp proxy
  credentials outside URL userinfo plus rendered-log redaction), `6ecbd8bd`
  (loop-handler redaction, HTTP(S)-only colon username rejection, SOCKS
  colon names preserved, `InvalidProxy` credential-safe message).
- Account and dashboard policy: `caad3d40` (usage deactivation only on
  explicit terminal signals), `a07ce563` (API-key secret `no-store` on
  `POST /api/api-keys/`; slashless alias omitted), `0ca5c724` (audit reads
  require admin), `80265ff8` (overview/request-log independent failure),
  `628b6206` (recoverable dashboard route shell).
- Transport and transcription: `e9100e5a` (SDK transcription fingerprint
  normalization), `02b61d5b` (keep-alive timer cleanup and 300s default;
  protocol-mode preservation; no h2c), `8afe0679` (release routed SSE
  responses; aiohttp/SOCKS/duck-typed only), `d771aa0f` (image-route
  start-time middleware is pure ASGI only; remaining stack may still use
  `BaseHTTPMiddleware`), `862efac3` (shared SSLContext implementation with
  no wire-contract change).
- Continuity and compact: `63ac6aee` (illegal reconstructed header
  fail-closed), `aec4d7b7` (canonical prompt-cache hard replica continuity
  via existing owner-forward), `b2c5ffcc` (compact
  failover after permanent refresh), `be9fa06f` (dedicated duplicate
  tool-call terminal; retry-circuit increment omitted), `da1dce6d` (fork-
  specific ordered health writes only; default settlement still awaits;
  cancellation may transfer tracked cleanup; public/log code stays
  `previous_response_owner_unavailable`).

### Explicit skips

- `dee12b95` / `e845a25e`: Rust/native egress.
- `dd28d7df`: excluded bridge-ring lifecycle.
- `018659d3`: absent retry-circuit symbols (parent confirmed).
- `4d6fada9`: `_load_balancer/` decomposition.
- `1c54f9ae`: unrelated upstream CI / model-source spec.
- `220a9798`: line-count formatting.
- `5ad638b6`: routine dependency bumps.
- `887cba30`: already ported via `39dedee4`.
- `7e1c1e82` (ignore detached durable bridge owner): skipped unsupported
  detach lifecycle. Known fork producer trace has no writer of the full
  `CLOSED` / account-none / owner-none / anchors-none shape;
  `release_session` preserves account plus anchors and FK deletion only
  clears account. Not worthwhile beyond manual rows.
- `b328cc97` (`#2014` accepted background JSON): depends on absent
  `82a58aff` `#1995` native `stream:false` parity; fork always-SSE mode
  does not hit it.
- `0174a278` / `0a726558`: omitted as absent upstream-only startup/recovery
  infrastructure (`seed_hard_sticky_outage_grace_on_startup`,
  `get_routing_availability_cache.refresh_from_db`, and
  http-bridge-recovery-settlement/reaper names).
- Remaining CPU optimizations `0b127a9c`, `f39539db`, `55db6d77`,
  `2cf2efe7`, `972a7341`, `4808f638`: deliberate omission from this
  bug/security batch due validation/lock/serialization/history semantics,
  with no fork-specific performance proof.

### Fetched non-main branches

The inventory contained 309 `origin/*` tips not merged into `origin/main`.
This is an inventory, not a claim that every historical branch was reviewed.
The follow-up review covered the non-main branches changed or introduced by
this fetch:

- Adopted the WebSocket-only part of `f035dcce`, with required pair-safety and
  client-replay dependencies from `ba4f80fd`, `abbd3dda`, `ca3f05cf`,
  `3eca7ff2`, and `d786efd6`. Fresh retries remove response-owned tool-search
  IDs from copies only after establishing completed-compatible, ordered,
  self-contained client-owned pairs. Server-owned, orphan, incomplete, and
  reused-call-ID histories cannot become fresh retries. HTTP compact,
  `replay_safety.py`, and normal anchored trimming remain unchanged.
- Skipped detached-owner tip `6a179327` for the same unsupported lifecycle as
  `7e1c1e82`.
- Skipped spool-timeout tip `5c769fcc`: its event batcher is absent in this fork
  and its tests assume the excluded bridge-ring lifecycle.
- Skipped the new `takeover/sim-harness`, `sim-harness-guard`, and `sim-wp2` /
  `sim-wp3` / `sim-wp4` framework branches and release metadata tips.

### Local verification

- The originally committed 25 changed Python test files passed: 1,942 tests.
  A later follow-up made the HTTP-bridge integration autouse fixture join
  leftover retired-session readers after `close_all_http_bridge_sessions()`.
  That is test-harness teardown, not a production `close_all` change.
  Production still closes registered sessions and then drains scheduled
  background closes. The whole `tests/integration/test_http_responses_bridge.py`
  file then passed 100 tests with `PytestUnraisableExceptionWarning` and
  `RuntimeWarning` treated as errors. Two httptools-triggered websockets
  deprecation warnings remain in the keep-alive selector file.
- Four focused frontend files passed: 23 tests. Frontend no-emit typechecking,
  focused ESLint, targeted Python typechecking, and Ruff lint/format checks on
  all 53 changed Python files passed.
- An isolated Chromium smoke against the local Vite server exercised overview
  failure, keyboard Retry recovery, unknown-route recovery, and recovery after
  a blocked settings import. API responses were fixtures and external requests
  were blocked. The real CLI, with a database-free ASGI application substituted,
  served HTTP 200 through its `auto` protocol configuration. Both servers were
  stopped after proof.
- Strict validation passed for all 19 selected OpenSpec changes. Canonical
  strict validation returned 25 passed and 14 failed on both this tree and the
  unchanged `3aabf89f` baseline. Those inherited failures concern placeholder
  Purpose sections and duplicate Responses requirement names.
- Whole-repository formatting also found ten unchanged files needing formatting;
  they were not rewritten by this batch.
- Full builds, full test suites, and coverage were left to CI. Change artifacts
  remain active for publication/CI closeout. No deployment or production smoke
  was performed.
