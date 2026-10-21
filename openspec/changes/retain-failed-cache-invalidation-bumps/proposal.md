# Retain failed cache invalidation bumps

## Why

API-key and firewall mutations clear the local cache and then publish a version
bump to the `cache_invalidation` table so peer replicas clear theirs on their
next 0.5 s poll. `CacheInvalidationPoller.bump()` attempts that write exactly
once and only logs a warning on failure. After a transient database error the
mutation is committed but no peer ever learns of it, so other replicas keep
serving stale API-key or firewall state until the 60 s cache TTL backstop (or
indefinitely for caches without one).

## What Changes

- A bump whose write does not complete (error or cancellation) records its
  namespace as pending on the poller.
- The poller's existing run loop re-publishes pending namespaces at the start of
  every tick, without creating new tasks, until the write succeeds.
- Callers of `bump()` keep the same signature and never see the failure.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `query-caching`: invalidation publication MUST be retained and retried until
  it succeeds.

## Impact

- `app/core/cache/invalidation.py`
- `tests/unit/test_cache_invalidation_poller.py`, `tests/integration/test_cache_invalidation_bus.py`
