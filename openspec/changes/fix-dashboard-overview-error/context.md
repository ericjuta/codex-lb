# Dashboard overview terminal-error context

## Purpose

Separate an initial pending query from a terminal failure that has no overview
data, while retaining healthy shell and cached-data behavior.

## Decision

Pending no-data state keeps the existing skeleton. Terminal no-data state uses
the existing alert and button primitives. Bounded presentation state retains
each timeframe's error while TanStack Query clears its live error during
refetch. The busy state clears for that timeframe when its request settles;
the retained error clears only after that timeframe succeeds.

## Constraints

- Retry only the overview query.
- Do not change retry count, query key, API, shell, or global alert behavior.
- Cached overview content remains visible on later refetch errors.
- No timing waits or polling in tests.

## Upstream Evidence

- Upstream commit: 80265ff8552d4aaface0497d4035561b3200fb01 (#2017)
- Upstream verification: integration test covering failure/retry/recovery flow and timeframe transition isolation

## Example

The overview endpoint exhausts retries with HTTP 503. The shell remains, the
skeleton disappears, an alert and Retry appear, Retry becomes busy during the
single refetch, and recovered overview content replaces the error.
