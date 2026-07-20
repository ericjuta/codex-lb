#!/usr/bin/env bash
# burn_report.sh - live codex-lb burn / cache / runway report.
#
# Companion to .agents/skills/codex-lb-burn-audit/SKILL.md.
# Reads only from the local Postgres container; no credentials or account
# secrets are embedded. Account IDs in output come from your local DB.
#
# Usage: scripts/burn_report.sh [DEPLOY_SPLIT_TS]
#   DEPLOY_SPLIT_TS  optional 'YYYY-MM-DD HH:MM:SS' UTC timestamp to split
#                    pre/post-deploy cache stats. Defaults to the app
#                    container's start time.
set -euo pipefail

APP_CONTAINER="${CODEX_LB_CONTAINER_NAME:-codex-lb-direct}"
PG_CONTAINER="${CODEX_LB_PG_CONTAINER_NAME:-codex-lb-postgres}"
PG_USER="${CODEX_LB_PG_USER:-codex_lb}"
PG_DB="${CODEX_LB_PG_DB:-codex_lb}"

psql_run() {
  docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -c "$1"
}

split_ts="${1:-}"
if [[ -z "$split_ts" ]]; then
  started="$(docker inspect -f '{{.State.StartedAt}}' "$APP_CONTAINER" 2>/dev/null || true)"
  if [[ -n "$started" ]]; then
    split_ts="$(date -u -d "$started" '+%Y-%m-%d %H:%M:%S')"
  fi
fi

echo "== codex-lb burn report ($(date -u '+%Y-%m-%d %H:%M:%S') UTC) =="
echo "app container: $APP_CONTAINER  deploy split: ${split_ts:-<none>}"

echo
echo '-- Weekly usage per account (usage_history, primary window) --'
psql_run "
SELECT account_id, used_percent,
       to_timestamp(reset_at) AT TIME ZONE 'UTC' AS reset_at_utc,
       recorded_at
FROM usage_history uh
WHERE \"window\"='primary'
  AND recorded_at = (SELECT max(recorded_at) FROM usage_history
                     WHERE account_id = uh.account_id AND \"window\"='primary')
ORDER BY account_id;"

echo
echo '-- Fleet points + runway --'
psql_run "
WITH latest AS (
  SELECT DISTINCT ON (account_id) account_id, used_percent, reset_at
  FROM usage_history WHERE \"window\"='primary'
  ORDER BY account_id, recorded_at DESC
)
SELECT count(*)*100                             AS capacity_pts,
       sum(used_percent)                        AS used_pts,
       count(*)*100 - sum(used_percent)         AS pts_left,
       round((extract(epoch FROM (to_timestamp(min(reset_at)) - now()))/3600.0)::numeric, 1)
                                                AS hours_to_first_reset,
       round(((count(*)*100 - sum(used_percent)))::numeric
             / nullif((extract(epoch FROM (to_timestamp(min(reset_at)) - now()))/3600.0)::numeric, 0), 2)
                                                AS sustainable_pts_per_hour
FROM latest;"

echo
echo '-- Fleet points hourly trend (12h) --'
psql_run "
SELECT hr, sum(max_used) AS fleet_pts FROM (
  SELECT account_id, date_trunc('hour', recorded_at) AS hr, max(used_percent) AS max_used
  FROM usage_history
  WHERE \"window\"='primary' AND recorded_at > now() - interval '12 hours'
  GROUP BY 1,2) s
GROUP BY 1 ORDER BY 1;"

echo
echo '-- Per-model cache + uncached burn (last 6h, request_logs) --'
psql_run "
SELECT model, count(*) AS reqs,
       round(100.0*sum(cached_input_tokens)/nullif(sum(input_tokens),0),1) AS cache_pct,
       round((sum(input_tokens - cached_input_tokens))::numeric/count(*),0) AS uncached_per_req,
       sum(input_tokens - cached_input_tokens) AS uncached_total,
       sum(output_tokens) AS output
FROM request_logs
WHERE requested_at > now() - interval '6 hours' AND status='success'
GROUP BY model ORDER BY uncached_total DESC NULLS LAST;"

if [[ -n "$split_ts" ]]; then
  echo
  echo "-- Per-model cache pre/post deploy split ($split_ts UTC) --"
  psql_run "
SELECT CASE WHEN requested_at < '$split_ts' THEN 'pre' ELSE 'post' END AS phase,
       model, count(*) AS reqs,
       round(100.0*sum(cached_input_tokens)/nullif(sum(input_tokens),0),1) AS cache_pct,
       round((sum(input_tokens - cached_input_tokens))::numeric/count(*),0) AS uncached_per_req
FROM request_logs
WHERE requested_at > now() - interval '24 hours' AND status='success'
GROUP BY 1,2 ORDER BY model, phase DESC;"
fi

echo
echo '-- Hourly uncached-token burn (24h, all models) --'
psql_run "
SELECT date_trunc('hour', requested_at) AS hr, count(*) AS reqs,
       round((sum(input_tokens - cached_input_tokens)/1000000.0)::numeric, 2) AS uncached_M
FROM request_logs
WHERE requested_at > now() - interval '24 hours' AND status='success'
GROUP BY 1 ORDER BY 1;"

echo
echo '-- Top burn sessions (last 6h) --'
psql_run "
SELECT model, session_id, count(*) AS reqs,
       round(100.0*sum(cached_input_tokens)/nullif(sum(input_tokens),0),1) AS cache_pct,
       round((sum(input_tokens - cached_input_tokens))::numeric/count(*),0) AS uncached_per_req
FROM request_logs
WHERE requested_at > now() - interval '6 hours' AND status='success'
GROUP BY 1,2 ORDER BY sum(input_tokens - cached_input_tokens) DESC LIMIT 10;"
