# Tasks: improve-sticky-failover-affinity

- [x] 1. Add `sticky_selection_total` counter to `app/core/metrics/prometheus.py` (both branches + `__all__`)
- [x] 2. Thread `excluded_ids` into `_select_with_stickiness`; preserve mapping when pinned account is excluded-only; record outcome metric at all return paths
- [x] 3. Unit tests: excluded-pinned preserves mapping (prompt_cache + codex_session), non-pool pinned still deletes, outcome metric coverage
- [x] 4. Run focused tests + ruff + openspec validate
- [x] 5. Deploy via update.sh and verify live metric/log behavior
