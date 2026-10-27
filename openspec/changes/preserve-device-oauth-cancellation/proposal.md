# Proposal

## Why

The historical device-flow cancellation test timed out under suite load. Source inspection identifies a real cancellation-loss window: route-resolution session cleanup catches `BaseException`, so a superseded poll can resume into token exchange after its cancellation was consumed. The historical timeout itself has no retained task stack establishing that exact cause.

## What Changes

- Preserve outstanding cancellation at the OAuth route boundary after database cleanup completes.
- Exercise replacement while the previous poll is in token exchange, route-session rollback, and route-session close, using explicit event barriers and the real session cleanup helpers.
- Keep the one-second cancellation guard; drain test-owned poll tasks even on assertion failure.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-architecture`: specify device OAuth replacement cancellation across route-session cleanup.

## Impact

OAuth service routing and its integration regression test only; no database-helper contract, API schema, dependency, or deployment changes. The shared OAuth route boundary also preserves cancellation for existing browser/code-request callers. Validation is handed off rather than claimed as executed.
