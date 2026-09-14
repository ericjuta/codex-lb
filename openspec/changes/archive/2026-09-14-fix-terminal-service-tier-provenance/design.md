## Context

The initial created response is useful for stable IDs and output reconstruction, but its service tier is not a final processing report. Continuation currently copies that initial field into the terminal response. Direct collection and WebSocket finalization then treat the copied value as actual. Separately, any-event collection retains created-only tiers when completion omits the field, and a finally-block counter can count unsuccessful attempts.

## Decisions

1. The final upstream terminal owns its service-tier field. Reconstruction copies that field when present and removes any inherited field when absent. Synthetic incomplete output removes created tier claims.
2. Streaming actual-tier evidence requires an explicit nonblank tier on `response.completed`. Failed, incomplete, cancelled and interrupted attempts do not gain evidence from earlier events. Hidden-round completions do not supply the final logical request's actual tier.
3. Billable `service_tier` remains a separate fallback. Existing observed-event/request fallback is retained; explicit final terminal data takes precedence. This repair does not redesign multi-round pricing or historical accounting.
4. The existing mismatch counter is gated on successful completion and actual terminal evidence. Compact success is terminal by definition. Counter names, labels and transport coverage stay unchanged.
5. An explicit terminal `auto` is faithfully recorded but remains inconclusive about upstream scheduling. Neither a zero counter nor an absent tier proves Fast delivery.

## Verification and rollout

Use synthetic created, terminal, hidden-round, omitted-tier and interrupted-stream fixtures through folding and service/route settlement. Keep useful existing accounting assertions. Run all checks only after worker edits settle. Publish to ericjuta/codex-lb main through a reviewed PR, then use the existing direct deployment script with unchanged configuration. Verify image/source identity, readiness and safe error counts. Inspect grouped post-deployment metadata from ordinary traffic only, without prompts, response bodies, account identities or model benchmarks.

## Risks and rollback

New logs will have null actual tiers for created-only observations. Existing rows are not rewritten and must be separated from post-deployment observations by time. The deployment restarts the local proxy and interrupts in-flight connections. Keep the previous image available for rollback; do not change continuation or transport settings to make the evidence look better.
