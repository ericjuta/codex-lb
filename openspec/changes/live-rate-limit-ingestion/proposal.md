## Why

codex-lb learns account quota state exclusively by polling `/backend-api/wham/usage` (default every 60s, one account per scheduler tick). Upstream codex clients also consume fresher signals that ride on proxied traffic: `x-codex-{primary,secondary}-*` response headers and terminal `codex.rate_limits` stream events. Live evidence shows that successful-response headers can be provisional and disagree with the terminal event, so persisting both makes weekly usage oscillate between snapshot families. Selection state still needs per-turn signals to avoid lagging real usage by up to a refresh interval, but successful streams require one authoritative snapshot.

## What Changes

- Proxied upstream responses become a passive usage source: terminal `codex.rate_limits` events observed on successful HTTP/SSE and WebSocket streams are parsed into snapshots and written through the existing usage-history semantics. Rate-limit response headers are persisted only for error responses, where no terminal event may follow.
- Models assigned to a separate additional-quota lane are excluded from shared live usage ingestion, so their events cannot overwrite the dashboard's shared weekly meter.
- A per-account ingest throttle (change fingerprint + minimum write interval) bounds write volume; ingestion never blocks or fails the serving path, and publishes through a startup-registered hub so the core client layer stays decoupled from module-layer persistence.
- The background poller remains authoritative for accounts without live traffic and for payload-only fields; live rows naturally satisfy its freshness gate, so polling pressure drops on busy accounts without configuration changes.
- Ingestion is enabled by default with an env kill switch.

## Capabilities

### New Capabilities

- `live-usage-ingestion`: passive per-turn usage snapshots from proxied traffic.

### Modified Capabilities

None (usage-refresh-policy semantics are unchanged; live rows flow through the same storage contract).

## Impact

- Code: `app/core/usage/live_snapshots.py` (new), `app/core/usage/live_hub.py` (new), `app/modules/usage/live_ingest.py` (new), `app/core/clients/proxy.py`, `app/modules/proxy/_service/streaming/mixin.py`, `app/modules/proxy/_service/http_bridge/upstream_events.py`, `app/modules/proxy/_service/websocket/mixin.py`, `app/main.py`, `app/core/config/settings.py`
- Tests: parser/ingestor unit suites, SSE and bridge integration coverage
- Specs: `openspec/specs/live-usage-ingestion/spec.md` (new)
