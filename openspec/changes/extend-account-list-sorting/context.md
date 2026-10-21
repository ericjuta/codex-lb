# Context

## Purpose

Let operators order the Accounts list by status or by how much 5-hour, weekly, or monthly quota is left.

## Upstream provenance

Hand port of upstream `72630bbfe` (#2578). The sorting logic, option labels, and unit test cases follow
upstream. Skipped: upstream's `docs/usage-reporting.md` note (docs are not edited here), its
en/ko/zh-CN locale keys (the fork's Accounts list does not read `accounts.sort.*`; labels are literal
strings in `ACCOUNT_SORT_OPTIONS`), and its before/after screenshots. The component test was added to the
existing `account-list.test.tsx` instead of a new file.

## Decisions

- Status order is active, paused, rate-limited, quota-exceeded, reauth-required, deactivated, using
  `normalizeStatus`; unrecognized statuses map to active, matching the rest of the dashboard.
- Unknown quota is `+Infinity` in the sort key, so `Number.isFinite` places it last for both
  directions without a second code path.
- `compareResetTimestamps` was renamed `compareKnownNumbers` because it now orders non-reset values.

## Failure modes

- Accounts whose usage has not been fetched yet have no percentages and always list last in quota modes.
- Quota modes sort by percentage, not credits, so accounts with different plan sizes are compared by fraction left.

## Example

Monthly quota (lowest remaining) lists an account at 0% before one at 80%, and an account with no monthly
data after both; switching to highest remaining lists 80%, 0%, then the unknown account.
