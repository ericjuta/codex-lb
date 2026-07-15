## Purpose and scope

This change closes related chronology gaps in routing, live WebSocket evidence ingestion, and account-summary display recovery.

## Decision rationale

The precise runtime marker is the only available value that preserves ordering within the second. The persisted whole-second marker remains appropriate for peer-worker cooldown enforcement, but it cannot distinguish two events in the same second.

## Constraints and non-goals

- Keep the existing persisted cooldown and compare-and-set recovery paths.
- Do not change database precision or add a migration.
- Do not alter sticky-session fallback or reallocation policy.
- Do not make tests wait for wall-clock delays.
- Preserve the existing fire-and-forget live-ingestion boundary.
- Keep account APIs and proxy routing free of new cross-module dependencies.

## Failure mode

If a usage row is written at `1700000000.7`, a rate limit occurs at `1700000000.8`, and `blocked_at` is persisted as `1700000000`, comparison with only the persisted value incorrectly treats the usage row as post-block evidence. After the short local backoff, the account can become active and receive another upstream attempt.

The precise marker must also survive selection-state synchronization. Otherwise the first pass remains safe but writes `1700000000` back into runtime state, and the next pass incorrectly accepts the `.7` usage sample.

## Concrete example

For the sequence above, early recovery must compare `1700000000.7` with the exact runtime boundary `1700000000.8`. Because the sample is older, the account remains rate-limited and retains its reset deadline.

## Operational notes

No rollout knobs or migrations are required. Validation should include the deterministic state-level regression and the existing sticky-session integration test in serial and xdist modes.

Direct Responses WebSocket traffic must produce the same passive usage snapshot as bridge traffic. A blocked account with positive credits recorded before its block must remain `rate_limited` in `/api/accounts` until qualifying post-block evidence exists.
