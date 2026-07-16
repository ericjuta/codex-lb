## 1. Core parsing and hub

- [x] 1.1 `app/core/usage/live_snapshots.py`: typed snapshot dataclass + parsers for x-codex response headers and `codex.rate_limits` event payloads.
- [x] 1.2 `app/core/usage/live_hub.py`: publish/no-op hub with startup registration.

## 2. Ingestor

- [x] 2.1 `app/modules/usage/live_ingest.py`: bounded queue (drop-oldest), single consumer with its own background sessions, per-account fingerprint + min-interval throttle, usage-history writes with credits fields and an enqueue-time snapshot observation timestamp retained across delays, selection-cache invalidation on write.
- [x] 2.2 Settings: `live_usage_ingestion_enabled` (default true), `live_usage_write_min_interval_seconds` (default 5), queue size; startup wiring in main.py.

## 3. Tap points

- [x] 3.1 HTTP/SSE: publish header snapshots for error responses and event snapshots on `codex.rate_limits` blocks in `_stream_responses_with_session`.
- [x] 3.2 WS bridge: publish event snapshots for `codex.rate_limits` frames in the upstream relay.

## 4. Validation

- [x] 4.1 Unit: parser edge cases including header and raw event-text numeric overflow; throttle fingerprint/interval; queue overflow drop-oldest; hub no-op; snapshots capture observation time before enqueue and sibling rows share it.
- [x] 4.2 Integration: SSE stream with rate-limit event writes rows for the serving account; kill switch produces no writes.
- [x] 4.3 `openspec validate live-rate-limit-ingestion --strict`; targeted proxy/usage suites.

## 5. Successful-stream snapshot precedence

- [x] 5.1 Restrict HTTP/SSE response-header ingestion to upstream errors so successful headers cannot overwrite terminal event snapshots.
- [x] 5.2 Add routed-stream regressions for conflicting successful headers/event precedence and error-header persistence.
- [x] 5.3 Run strict OpenSpec validation, focused tests, static checks, and final diff inspection.
