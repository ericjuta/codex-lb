# Context: share-outbound-ssl-context

## Purpose and scope

Reuse one process-wide verification `SSLContext` across outbound connectors.
This is not a TLS policy change and does not add native egress.

## Decision

`_shared_ssl_context` is a `functools.cache` wrapper that calls
`_build_ssl_context` at lookup time so tests can still patch the constructor.
`_reset_shared_ssl_context` and `close_http_client()` clear the cache.

## Constraints

- `verify_mode`, `check_hostname`, minimum protocol, options, and trust store
  MUST match a fresh `_build_ssl_context()` build.
- Nothing mutates the context after construction.

## Failure modes

- A poisoned cache after a constructor patch leaks across tests; unit tests
  reset the cache around each case.
- CA files updated on disk are invisible until process restart.

## Example

Two `TCPConnector` constructions in one process receive the same
`SSLContext` instance. A third construction after `close_http_client()`
builds a new instance with the same verification policy.

## Upstream provenance (not this fork's proof)

Upstream 862efac3 measured ~7.5 ms CPU and ~650 KB RSS per copy on x86
Python 3.14. Local verification is parent-owned.
