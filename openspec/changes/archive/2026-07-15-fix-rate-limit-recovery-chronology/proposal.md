## Why

Rate-limit chronology is inconsistent across three serving and status surfaces: the marking worker can compare against a truncated persisted timestamp, direct Responses WebSockets do not publish live rate-limit frames, and account summaries can display a blocked account as active from pre-block credit evidence. Together these gaps can cause premature retries, delayed routing evidence, and dashboard state that disagrees with routing.

## What Changes

- Require the marking worker to evaluate early-recovery usage against its precise in-memory rate-limit event timestamp.
- Publish direct `/v1/responses` and `/backend-api/codex/responses` WebSocket `codex.rate_limits` frames through the existing live-usage hub.
- Require account-summary recovery from a persisted rate limit to use qualifying usage evidence recorded after `blocked_at`.
- Preserve the persisted cooldown and peer-worker recovery rules.
- Add deterministic subsecond regression coverage while keeping the existing sticky-session retry contract unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `account-routing`: Tighten rate-limit early-recovery chronology so only usage recorded after the exact local block event can reactivate an account.
- `live-usage-ingestion`: Cover direct Responses WebSocket relays under the same passive ingestion contract as HTTP/SSE and bridge traffic.

## Impact

- Affected code: account selection, direct WebSocket relay ingestion, and account-summary status mapping.
- Affected tests: focused chronology, direct relay ingestion, and `/api/accounts` status coverage; existing sticky-session integration expectations remain unchanged.
- No API, schema, migration, dependency, or configuration changes.
