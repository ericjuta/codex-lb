---
name: codex-lb-burn-audit
description: Audit live codex-lb quota burn rate, project remaining weekly headroom to reset, and measure prompt-cache hit rates per model. Use when asked about burn rate, quota/credits left, "how much left by reset", usage per hour, cache-fix effectiveness, or which model lane is consuming fleet quota.
---

# codex-lb Burn Audit

Answer burn-rate / runway / cache-effectiveness questions from live data. Runtime defaults:
app container `codex-lb-direct` (see `CODEX_LB_CONTAINER_NAME` in `update.sh`), Postgres
container `codex-lb-postgres` (user/db `codex_lb`, UTC).

## Source-of-truth map

| Question | Use | Do NOT use |
|---|---|---|
| Real weekly usage % per account | `usage_history` table, `window='primary'` (`window_minutes=10080` = weekly, despite the name) | Balancer log lines |
| Per-request tokens / cache hits / model mix | `request_logs` table | — |
| Burn attribution pre/post a deploy | `request_logs` split on deploy timestamp (container start time approximates deploy) | — |
| Account status / plan / paid-credit balance | Dashboard | — |
| `remaining_credits=` in balancer logs | Nothing. It is a **derived score**: `capacity*(1-used%)` with synthetic per-plan fallback capacity, lane-scoped under gated routing. Misleading for burn accounting. | Never sum/diff these across log lines |
| `window='secondary'` rows in usage_history | May be stale on some deployments; check `max(recorded_at)` before trusting | — |

Key units: fleet capacity = `num_accounts * 100` points (1 pt = 1% of one account's weekly
window). Models gated by an additional quota (see `config/additional_quota_registry.json`,
`additional_usage_history` table) meter on their own lane; other models share the weekly
meter. Don't mix lanes in one runway number.

## Workflow

1. Run `scripts/burn_report.sh` (optional arg: deploy split timestamp, default: container start).
2. Compute runway: `pts_left = capacity - current fleet sum`; hours to reset from `reset_at`.
   Sustainable pts/h = pts_left / hours_to_reset.
3. Project with day-shape, not flat average: measure idle-hours vs active-hours slope from
   the hourly trend and give a scenario range (recent-day actual / current blended / peak-hours
   sustained), not a single number.
4. Cache verdict: compare per-model `cache_pct` pre/post deploy split. Canary thresholds live
   in container env `CODEX_LB_PROMPT_CACHE_CANARY_*`.
5. Report uncached input tokens (`input - cached`) per model to name the burn driver; gross
   token volume is misleading when cache rates diverge across models.

## Gotchas

- `docker logs --since Nh` + grep pipelines: balancer "gated routing"/"winner" lines interleave
  across concurrent requests; pairing them with awk mis-attributes lanes. Don't.
- `upstream_websocket_open_timeout` storms are typically transient upstream capacity; classed
  retryable and absorbed by failover, not an outage. Count them, don't panic. They hit all
  accounts uniformly and follow a diurnal shape (quiet ~03-05 UTC); direct socket probes show
  chatgpt.com edge stalls while other Cloudflare-fronted hosts connect instantly. Local knobs
  live in `.env.local`: `CODEX_LB_UPSTREAM_CONNECT_TIMEOUT_SECONDS` (2026-07-15: 12; keep >8s
  to absorb the 3-8s SYN-stall band) and `CODEX_LB_PROXY_UPSTREAM_WEBSOCKET_CONNECT_LIMIT`
  (2026-07-15: 16; at 4 the admission gate serialized handshakes during storms). If continuity
  fail-closed events rise after lowering the timeout, split the difference (e.g. 15s).
- `eligible_accounts=N-1/N` on gated-quota routing = one account exhausted that lane; expected.
- Dashboard "Credits 0.00" = no paid overflow balance, NOT zero weekly quota remaining.
- Client-side model/reasoning config (e.g. `~/.codex/config.toml`) only affects that client's
  traffic; fleet burn is usually dominated by automated lanes upstream of this repo.
