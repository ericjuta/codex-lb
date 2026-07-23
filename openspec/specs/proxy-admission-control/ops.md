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
