# Context

## Purpose

Make a revoked workspace leave the pool and move the request, instead of retrying a dead account.

## Upstream provenance

Narrow port of upstream `3d8fa7ba6` (#2573). Skipped: the `retry.py` keyed-health hunk, owner_bound plumbing
and the urllib3 bump (owned by another lane).

## Decisions

- Only the exact structured code classifies as `account_unavailable`; a payment incident also uses 402.
- Keyed requests defer the permanent write through the existing pending-penalty / deferred-permanent-health path.

## Failure modes

- Last candidate account: the upstream error is surfaced (failover_decision returns `surface`).

## Example

Account A returns 402 `deactivated_workspace`; the request is served by account B; A is DEACTIVATED.
