## Why

Operators with many accounts cannot order the Accounts list by health. Finding the
accounts that are closest to exhausted, or that are not active, means scanning every
row. The sort selector (see `add-account-list-sort-modes`) only offers reset time,
reset credits, and name.

## What Changes

- Add ascending and descending Accounts sort modes for account status and for
  remaining 5-hour, weekly, and monthly quota percentage.
- Treat missing quota values as unknown and sort them after known values in both
  directions; zero remaining is a known value.
- Keep all existing sort modes and the default (`most_reset_credits`) unchanged.

## Impact

- Affected spec: `frontend-architecture`.
- Affected code: `frontend/src/features/accounts/sorting.ts` and its tests. The
  Accounts UI in this fork uses literal English labels, so no locale keys change.
