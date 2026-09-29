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

## 2026-09-21 upstream image host pick (`#2320`): scope and skips

A single narrow port from upstream PR
[`#2320`](https://github.com/Soju06/codex-lb/pull/2320), commit
`92c7f6201a8fd31d6160570f60ee59db5686dd67`, archived change
`2026-09-21-use-luna-image-host`. Only the internal host-model choice for
`/v1/images/generations` and `/v1/images/edits` is adopted. Its normative
requirement is now carried by the canonical `images-api-compat` spec.

### Adopted

- `app/core/openai/host_models.py`: `resolve_default_host_model() -> str`. It
  reads the in-memory model registry and walks the candidate order
  `gpt-5.6-luna`, then `gpt-5.5`, selecting the first slug whose
  `plan_types_for_model(slug)` is non-empty and whose `is_suppressed_model(slug)`
  is false. If neither qualifies it returns Luna.
- Both image handlers in `app/modules/proxy/api.py` call the resolver instead of
  reading a configured host.

Registry visibility includes bootstrap fallback, but is not account entitlement.
A selected host can still be rejected by normal account
routing, authentication, and suppression behavior downstream; the resolver
performs no discovery, network request, account probe, or retry.

### Operator-visible change

The `images_host_model` setting is removed and the host becomes code-owned.
There is no alias or migration shim. Any surviving `images_host_model`
override in a deployed environment is obsolete and should be dropped during a
separately authorized configuration change. No LB envfile or credentials
changed during this local deployment; the effective environment was unchanged.

Unchanged: the public `gpt-image-*` contract and the `gpt-image-2` default via
`images_default_model`, API-key model policy, usage accounting, request-log
model identity, translation signatures, and the remaining image setting
`images_max_partial_images`. There is still no `images_max_n` setting; the
existing single-image limit is unchanged.

For example, if Luna has no plan visibility but `gpt-5.5` is visible and
unsuppressed, a public `gpt-image-2` request uses `gpt-5.5` internally. Its
public response and accounting still use the image model.

### Explicit skips

This port retains the fork exclusions recorded above. It does not change:

- Account probes and catalog discovery changes.
- Upstream model-source routes (see the `1c54f9ae` skip above).
- The `_load_balancer/` decomposition (see the `4d6fada9` skip above).
- Retry-policy and authentication changes.

### Focused verification and local runtime proof

Completed on 2026-09-21:

```sh
uv run pytest tests/integration/test_proxy_images.py tests/unit/test_images_schemas.py tests/unit/test_images_translation.py tests/e2e/test_openai_sdk_compat.py::TestImages
# 184 passed, 0 failed
bunx --package @fission-ai/openspec@1.3.0 openspec validate use-luna-image-host --strict
# Change 'use-luna-image-host' is valid
```

Both public-route regressions failed under fault injection of the prior
`gpt-5.5` host behavior. Ruff check and format checks passed on
`app/core/openai/host_models.py`, `app/core/config/settings.py`,
`app/modules/proxy/api.py`, `tests/integration/test_proxy_images.py`, and
`tests/e2e/test_openai_sdk_compat.py`; all five were already formatted. Targeted
ty checks with `--output-format concise` passed on those three application
files. Full repository suites were not run.

`bash ./update.sh` replaced only the local `codex-lb-direct` application with
image `codex-lb-server:local-image-role-8b26bca18b5f`. Startup and health checks
passed, and the three deployed application files matched the checkout by hash.
The deployment included uncommitted changes; its revision label is not proof
of a clean committed source tree. Nothing was pushed or merged, and no remote
deployment was performed.

Runtime settings stayed unchanged: `codex-lb-data` volume, `codex-lb-net`
network, eight workers, metrics enabled on 9090, 6 GiB memory, six CPUs, and
8,192 PIDs. Ports 1455, 2455, and 9090 remained bound to loopback. The LB
envfile, effective environment, and credentials were unchanged.

A real OMP SDK session-wrapped `generate_image` smoke from the verified source
tree used `codex-lb/gpt-image-2` with provider fallbacks disabled. One generation
and one edit returned PNGs. Visual inspection confirmed a red circle on white,
then a blue circle with composition retained. Both images were 1254x1254
despite a 1024x1024 size request, so this is not an exact-size promise. The
smoke proves local generation and editing, not observation of the actual
upstream host slug.

The patched OMP 18.2.7 binary was built with standalone Bun 1.4.2 and installed
locally. A fresh process recognized `codex-lb/gpt-image-2` as an image model and
resolved the image role to it. Four focused OMP test files passed 167 tests,
and the nonincremental TypeScript check passed. Existing OMP sessions need to
restart to load the patch. The original Homebrew binary, provider credential,
chat routing, and fallback configuration were preserved.

### Spec sync and archive

After that verification, the change's single normative requirement, "Image
routes select a code-owned Responses host model", was applied to the canonical
`openspec/specs/images-api-compat/spec.md` alongside the existing image
requirements, which were left unchanged. The completed change directory was
then moved verbatim, including `.openspec.yaml`, to
`openspec/changes/archive/2026-09-21-use-luna-image-host/`, leaving no active
duplicate.

The strict validation transcript above was produced while the change was still
active under its unprefixed name; it was not re-run for the archive move, and
no tests, builds, formatting, or deployment accompanied the sync and archive.
The local deployment described above reflects the tree before these commits.
Publishing the commits does not perform another deployment.

## 2026-09-29 fetched upstream batch: four narrow ports

Local source baseline: `4d8ece60e59d3720aaeaeb336f0c0245be2f504d`. This review
covers **28 commits introduced or changed by this fetch only**: 20 main-branch
entries as `origin/main` advanced from `3d23d53f8` to `f8ffbac20`, plus eight
non-main entries. It does not establish an upstream reviewed-through cutoff or
claim that older upstream history was evaluated. The 2026-09-05 `3aabf89f`
marker above is a fork-local baseline, not an upstream audit cutoff.

All 28 were classified; final disposition is four PORT / 24 SKIP. Sixteen
flagged entries received source review (`source_verified=true`); the twelve
maintenance/release/dependency entries were classified SKIP without a separate
source review (`source_verified=false`). Duplicate main/branch patches still
count as separate fetched entries, not separate adopted fixes.

### Adopted SHAs and fork-specific contracts

- `a3aa8caa0a18129e28b28944b389ab4dbd314b1c` (#2468),
  `validate-quota-planner-timezones`: trim and validate nonblank timezone input
  with `ZoneInfo` before settings persistence, HTTP 400
  `invalid_quota_planner` on invalid input, blank retention, and UTC fallback
  for malformed legacy keys without rewriting rows. Canonical capability:
  `quota-phase-planner`.
- `6b10052ecb18aa0daf2a19e2244aacbae22d1e47` (#2469),
  `preserve-file-failover-provenance`: retain typed routed-transport phase,
  error code, and replay eligibility through file operation failover. A
  returned finalize poll closes transport-failure failover eligibility on both
  routed and direct transports; the existing `401` forced-refresh/reselection
  path is unchanged, and pinned finalize ownership remains enforced.
  **Deliberate addition beyond upstream:** guard direct aiohttp polling too;
  upstream guarded only routed polling. Status/parse errors stay untyped,
  legacy first-poll classification is retained, and in-memory TTL file pins
  stay unchanged. Canonical capability: `responses-api-compat`.
- `f8ffbac2099a113fba54dfd8d77774f5bca80ffa` (#2496),
  `omit-unsupported-probe-token-limit`: omit `max_output_tokens` outright from
  the fixed direct Force Probe body. No replacement cap, setting, retry, or
  sanitizer. Other probe contracts are unchanged. This supersedes the older
  `1` and `16` output-token clauses. Canonical capability:
  `usage-refresh-policy`.
- `da70ac5d573314abc1237cdea170f599734908d1` (#2119),
  `require-spendable-credit-override`: usable secondary-window credit override
  requires unlimited credits or positive balance, not a bare has-credits flag.
  Proxy selection remains advisory; persisted future-reset blocks are respected
  and normal active-seed/cooldown behavior is unchanged. No #2078 cooldown/status
  semantics or upstream second credit requirement was imported. Canonical
  capability: `usage-refresh-policy`.

Not imported by any port: `_load_balancer/` decomposition, model sources,
`prohibit_fast_mode`/fast-mode policy, native Rust egress, persistent
`FileAccountPinRepository`, `with_dashboard_overrides`, or upstream probe-health
settlement (`record_account_probe_result`, `force_refresh_result`, and probing
recovery streaks). No new migrations, schemas, settings, or dependencies.

### Explicit skips (24 fetched entries)

Source-reviewed, not applicable to this fork (12 entries):

- `73f5f034a` (#2513): duplicate Content-Type is collapsed by the fork's aiohttp
  transports before the wire; upstream's replacement helper is absent.
- `3b75bb2d0` (#2255): upstream WebSocket drain tracking/pre-handshake close
  (#1520) is absent. The fork skips WebSockets in its in-flight middleware, so
  the rejection being fixed does not occur here.
- `70effa3a6` (#2484): SQLite bulk-history capping depends on upstream per-account
  cap/cutoff/floor infrastructure absent from the fork. The deployed database
  inventory was PostgreSQL, not SQLite.
- `ec9945999` (#2489): false-zero/dropped samples are unreachable from the fork's
  dense shared timestamp grid; upstream smoothing/remount state is absent.
  Cosmetic legend/tooltip differences are not adopted.
- `4725a105f` (#2460): dashboard-user ownership/cascade model and owner columns
  are absent, so the owner-row lock race has no fork counterpart.
- `09a140fa9` (#2461): SCIM/overflow merge parents are absent; importing them
  would break the fork's Alembic graph, which has no matching split head.
- `cd9b4084a` (#2329): opt-in migration benchmark depends on upstream-only
  revisions/tooling, not fork runtime behavior.
- `bd65477a6` (#2476): upstream's uv `0.12.13 → 0.12.19` patch does not match
  the fork's `0.11.25` pin. A deliberate minor-line bump needs its own container
  and frozen-lock proof; this patch is not adopted.
- `c6c16887d` / `14e959b26`: patch-equivalent viewport/drain test fix; upstream
  browser-smoke and graceful WebSocket process-shutdown test paths are absent.
- `4183216c9` / `bf386475f`: patch-equivalent native-packaging CI fix; the fork
  lacks `detect_changed_areas`/native backend area machinery, rejects Rust
  egress, and its CI has no such path-filter skip.

Maintenance/release/dependency churn classified SKIP without separate source
review (12 entries):

- `4dcf8f751`: metadata/pricing/Codex-version refresh; not imported into this
  fork-specific runtime batch.
- `3c4906eae`, `52b9a0d13`, `2913f4d57`, `e8cdb34f5`, `bcf0a969d`: CI action
  bumps.
- `18fc8955a`, `1493c17b1`, `2f61bc661`: dependency updates (frontend, Rust,
  Python).
- `74df98657`, `89e4def39`, `f986f7be5`: release/version metadata.

These skips are scoped to this fetched batch, not blanket findings on older
upstream history. They do not reverse the existing architectural exclusions.

### Local verification and evidence boundaries

Parent verification on the settled final application/test tree:

- `uv run --frozen pytest` on nine focused modules with `-q -p no:cacheprovider`
  and warnings-as-errors for `PytestUnraisableExceptionWarning` and
  `RuntimeWarning`: **377 passed**.
- `test_proxy_utils.py` and `test_codex_upstream_paths.py` with
  `-k 'files or file_ or transcribe or goal or codex_control or previsible or unary or failover'`
  under the same warning policy: **65 passed, 871 deselected**. Total:
  **442 passed**. This is focused verification, not the full repository suite.
- Ruff check and format check on seven changed application and eight changed
  test files: passed; all fifteen files already formatted.
- Repository-wide `uv run --frozen ruff check` and
  `uv run --frozen ruff format --check`: passed; **840 files** already formatted.
- A separate full-repository pytest run under the same warning policy timed out
  after **1200 seconds**. Its captured progress was not retained after the
  subprocess timeout; no failing or stalled test node was established. A later
  collection-only command succeeded with **6374 tests / 287 modules**. This is
  an inconclusive full-suite gate, not an additional passing-test claim or proof
  that the timeout predates these ports. No exact-command orphan remained.
- The CI-style four-worker runner with the Makefile's per-test watchdogs and
  the extra warning policy completed: **6317 passed, 56 skipped, 1 failed,
  15 warnings in 555.28 seconds**. The sole failure was
  `test_db_migrate.py::test_raw_usage_window_latest_index_migration_is_idempotent`:
  the extra `error::RuntimeWarning` rule promotes SQLAlchemy's existing
  expression-index reflection `SAWarning` to an error. The same node failed
  with the same warning in an isolated `HEAD` source snapshot, and passed
  (**1 passed, 2 warnings**) under the configured project warning policy on the
  current tree. No migration/source fix or warning suppression was added.
  This is not a claim that the extra-strict full-suite run was green.
- Parent LSP diagnostics returned only `OK` without diagnostic data. The tool
  limitation was reported; it is not a successful LSP diagnostics gate.

Standalone local smoke used disposable SQLite and loopback stubs only:

- Settings PUT with malformed/unknown timezone returned 400 without saving;
  valid trimmed and blank-retention updates worked. The full planner modules
  above cover malformed legacy stored values in forecasts and routing costs.
- Pure credit-service calls showed missing/zero/negative balances with the bare
  flag blocked in dashboard inference and persisted-future-block proxy modes;
  positive/unlimited credits retained the override. Advisory active-seed and
  cooldown behavior was not changed.
- The prior HEAD probe method fault-injected **in memory** returned
  `probeStatusCode: 400` against the rejecting loopback stub. The new method
  returned `200`, made exactly one upstream request, and sent only
  `input`, `instructions`, `model`, `store`, and `stream` body keys. No
  application/test files were rolled back for that fault injection.
- Real-socket file smoke: direct first refusal retained legacy `None` provenance
  and eligible failover; direct retry-response then refusal became typed `False`
  and non-replayable; routed first refusal was typed `True` and replayable;
  routed retry-response then refusal was typed `False` and non-replayable.

Probe rejection evidence from live Codex belongs to upstream #2496; it was not
reproduced against live upstream here. No production traffic, commit, push,
merge, deployment, or CI proof accompanied this closeout.

### Canonical sync and historical supersession

The four current deltas were intelligently synchronized: two ADDED timezone
requirements, two ADDED file requirements, one ADDED no-output-token probe
requirement, and the MODIFIED credit requirement. All unrelated canonical
requirements/scenarios were retained; the credit requirement's three original
scenarios were retained verbatim and one bounded bare-flag scenario was added.
Stable context is promoted to each capability's `context.md`.

`add-account-probe-endpoint` and `probe-valid-token-floor` were archived without
spec sync to `openspec/changes/archive/2026-09-29-<name>/`. Their existing tasks
and verification checkmarks were all complete; no fresh historical proof was
invented. `.openspec.yaml` was preserved for `probe-valid-token-floor`;
`add-account-probe-endpoint` had no such file. Their original deltas remain
verbatim history, headed by supersession notices in their proposals. **Do not
sync either historical delta:** neither the `1` nor `16` token clause is active.
Their old non-token endpoint/dashboard clauses were never synced and remain a
known canonical coverage gap, not a claim added by this batch.

Closeout validation used `npx --yes @fission-ai/openspec` because the installed
`openspec` launcher was a broken symlink. All four active changes passed
`validate <change> --strict`; `status --change <change> --json` reported all
planning artifacts done (`spec-driven`). Full canonical `validate --specs
--strict` returned **25 passed / 14 failed (39 items)**, matching the inherited
count recorded in the September 5 batch above. These are not a green
repository-wide strict gate: existing placeholder Purpose sections and
duplicate Responses requirement names remain. Validation specifically warns
that the file delta cannot be CLI-synced into the structurally duplicated
Responses spec. The agent-driven merge therefore added only its two distinct
requirements and retained all unrelated blocks; no unrelated spec repairs
were folded into this port. Archive moves must skip CLI spec synchronization
because current deltas have already been intelligently applied, and historical
deltas must never be applied.

An isolated `HEAD` OpenSpec snapshot was also strictly validated with the same
CLI: **25 passed / 14 failed**. Comparing blocking diagnostics by capability,
severity, and message while ignoring shifted line locations found **zero
introduced diagnostics**. Parent validation of the four archived deltas in an
isolated active layout, including the existing MODIFIED credit target, passed
**4/4 with no issues**.

Final review found no runtime blockers. It narrowed one documentation overclaim:
after a finalize poll response, only transport-failure failover is closed. The
existing unpinned `401` forced-refresh/reselection path is unchanged. The file
delta and canonical requirement were renamed and rescoped before archive, then
all four deltas passed strict validation again. With parent review clearance,
the four completed changes were moved verbatim, including `.openspec.yaml`, to
`openspec/changes/archive/2026-09-29-<change>/` without CLI spec resync.
