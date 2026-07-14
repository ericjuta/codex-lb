#!/usr/bin/env bash
# codex-lb burn report. Usage: burn_report.sh [DEPLOY_SPLIT_UTC e.g. "2026-07-14 14:30"]
# Env overrides: CODEX_LB_CONTAINER_NAME, CODEX_LB_PG_CONTAINER, CODEX_LB_PG_USER, CODEX_LB_PG_DB
set -euo pipefail
APP="${CODEX_LB_CONTAINER_NAME:-codex-lb-direct}"
PG="${CODEX_LB_PG_CONTAINER:-codex-lb-postgres}"
PSQL="docker exec $PG psql -U ${CODEX_LB_PG_USER:-codex_lb} -d ${CODEX_LB_PG_DB:-codex_lb}"
SPLIT="${1:-$(docker inspect -f '{{.State.StartedAt}}' "$APP" | cut -dT -f1,2 | tr T ' ' | cut -d. -f1)}"

echo "== Fleet weekly used% (hourly, last 8h; capacity = accounts * 100 pts) =="
$PSQL -c "SELECT hr, sum(pct) AS fleet_pts FROM (
  SELECT date_trunc('hour', recorded_at) hr, account_id, max(used_percent) pct
  FROM usage_history WHERE \"window\"='primary' AND recorded_at > now() - interval '8 hours'
  GROUP BY 1,2) t GROUP BY 1 ORDER BY 1;"

echo; echo "== Latest per-account =="
$PSQL -c "SELECT DISTINCT ON (account_id) left(account_id,8) AS account, used_percent, to_timestamp(reset_at) AS reset
FROM usage_history WHERE \"window\"='primary' ORDER BY account_id, recorded_at DESC;"

echo; echo "== Runway =="
$PSQL -c "WITH latest AS (
  SELECT DISTINCT ON (account_id) used_percent, reset_at
  FROM usage_history WHERE \"window\"='primary' ORDER BY account_id, recorded_at DESC)
SELECT count(*)*100 - sum(used_percent) AS pts_left,
  round(extract(epoch FROM (min(to_timestamp(reset_at)) - now()))/3600) AS hours_to_reset,
  round(((count(*)*100 - sum(used_percent)) / nullif(extract(epoch FROM (min(to_timestamp(reset_at)) - now()))/3600,0))::numeric, 2) AS sustainable_pts_per_h
FROM latest;"

echo; echo "== Per-model cache + uncached burn, split at deploy: $SPLIT UTC =="
$PSQL -c "SELECT CASE WHEN requested_at >= timestamp '$SPLIT' THEN 'post' ELSE 'pre' END era,
  model, count(*) reqs,
  round((sum(input_tokens)/1e6)::numeric,1) in_M,
  round((sum(cached_input_tokens)::numeric/nullif(sum(input_tokens),0))*100,1) cache_pct,
  round(((sum(input_tokens)-sum(cached_input_tokens))/1e6)::numeric,1) uncached_M
FROM request_logs
WHERE requested_at > timestamp '$SPLIT' - interval '24 hours' AND status='success'
GROUP BY 1,2 HAVING count(*) > 3 ORDER BY 2,1 DESC;"

echo; echo "== Log error codes (24h) =="
docker logs "$APP" --since 24h 2>&1 | grep -oE 'code=[a-z_]+' | sort | uniq -c | sort -rn | head -5
