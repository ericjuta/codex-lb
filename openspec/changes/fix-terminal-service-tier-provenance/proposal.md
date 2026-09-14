## Why

Continuation reconstruction can replace a terminal response's explicit service tier with the tier from the first `response.created`. Request logs and mismatch counters can therefore report `auto` even when the terminal reports `priority` or `default`. Created-only tiers and failed attempts must not be presented as successful terminal evidence.

## What Changes

- Preserve the final upstream terminal's service-tier field through continuation reconstruction, including its absence.
- Record streaming `actual_service_tier` only from an explicit successful completion, across direct streaming, native WebSocket, and the HTTP bridge.
- Keep the existing accounting-tier fallback separate from terminal evidence.
- Count service-tier mismatches only for successful completions with an explicit reported tier. Keep existing counter coverage and bounded labels.
- Verify the repaired response and request-log behavior with synthetic upstream events, then deploy and inspect aggregate normal-traffic metadata.

## Capabilities

### Modified Capabilities

- `responses-api-compat`: terminal tier preservation and actual-versus-accounting request-log semantics.
- `proxy-runtime-observability`: successful-terminal mismatch evidence and missing/auto interpretation.

## Impact

The change affects continuation reconstruction and proxy tier reporting. It adds no database columns or runtime settings, does not rewrite historical request logs, and does not alter request tiers, reasoning effort, transport, account selection, or continuation limits. Repairing reporting does not itself prove Fast delivery or improve model latency.
