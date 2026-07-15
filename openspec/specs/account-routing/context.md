# Account Routing Chronology Context

## Purpose and scope

The account-routing requirements preserve the true ordering between a local
rate-limit event and later recovery evidence. They cover runtime selection
state and account-summary display without changing sticky-session fallback or
reallocation policy.

## Decision rationale

The precise runtime block marker is the only available value that preserves
ordering within the second. The persisted whole-second marker remains useful
for peer-worker cooldown enforcement, but it cannot distinguish two events in
the same second. Runtime selection state therefore retains the precise marker
while the existing persisted compare-and-set recovery path remains intact.

## Constraints and non-goals

- Do not change database precision or add a migration.
- Keep persisted cooldown and compare-and-set recovery behavior.
- Do not alter sticky-session fallback or reallocation policy.
- Keep account APIs and proxy routing free of new cross-module dependencies.
- Keep regression tests deterministic rather than waiting on wall-clock time.

## Failure mode and example

Suppose a usage row is written at `1700000000.7`, a rate limit occurs at
`1700000000.8`, and the persisted `blocked_at` value is `1700000000`. Comparing
only with the persisted value incorrectly treats the usage row as post-block
evidence. The account can then become active after the short local backoff and
receive another upstream attempt.

Recovery instead compares the usage row with the exact runtime boundary. The
`.7` sample is older than the `.8` block event, so the account remains
rate-limited and retains its reset deadline. Selection-state synchronization
must preserve that exact marker so a later pass cannot regress to the rounded
value.

## Operational notes

No rollout knobs or migrations are required. Validation should include the
deterministic state-level regression and the sticky-session integration path in
both serial and xdist modes. The normative contract is in [spec.md](spec.md).
