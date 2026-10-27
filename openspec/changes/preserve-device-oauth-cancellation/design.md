# Design

## Context

See proposal.md for scope and motivation. Historical evidence is recorded in `openspec/specs/proxy-admission-control/ops.md`, under the 2026-10-21 batch: 1580 passed and one OAuth cancellation timeout; subsequent runs passed 3/3 alone, 32/32 in the module, and 3x39 with cache tests. Those are historical results, not validation of this change. The cancellation regression originated in commit `409a83ef5`.

The current source has a concrete interleaving:

1. The first device poll resolves its route inside `get_background_session()`.
2. The successful context exit awaits `close_session()`, which shields rollback/close.
3. A second start calls `remove_pending_device_flows_locked()`: it cancels and removes the first poll's flow under the store lock, then installs the replacement.
4. `_shielded()` finishes cleanup and re-raises `CancelledError`, but `_safe_rollback()` or `_safe_close()` catches `BaseException` and returns. Because cancellation arrived during a successful context exit, there is no body exception to re-raise.
5. `_oauth_route()` returns normally. The removed poll can enter token exchange and remain blocked despite its outstanding cancellation count. The original test's `wait_for(first_task, 1)` supplies another cancellation at its deadline and reports a timeout.

This is source-level evidence, not a captured stack from the historical failure. The old `sleep(0)` does not establish whether the poll reached token exchange or was still resolving/cleaning up its route.

## Goals / Non-Goals

**Goals:** preserve cancellation before OAuth upstream work resumes; make the three cancellation sites deterministic in the endpoint regression; drain test-owned tasks on failures.

**Non-Goals:** change shared database cleanup semantics, add cancellation deadlines/retries, redesign OAuth storage or reset, or assert that all historical timeouts had this cause.

## Decisions

- Move the route return outside the session context. After cleanup, check the current task's outstanding cancellation count and raise `CancelledError` before returning a route. This repairs the OAuth boundary for all four callers without changing their signatures or normal routing behavior.
- Keep shared session helpers untouched. Their existing tests explicitly require cleanup to outlive caller cancellation; changing their global behavior needs a separate caller audit.
- Parameterize the existing endpoint regression over token exchange, route rollback, and route close. Gate the first poll's actual session cleanup methods with events while retaining the real background-session context and cleanup helpers. The first route lookup belongs to the first start request; the second belongs to its poll, and the second start is held until that poll reaches the chosen gate.
- Keep the one-second poll-settlement guard, shield the observed task so the guard cannot manufacture the cancellation being tested, and use events instead of scheduling sleeps. Assert no old token exchange for cleanup cases, replacement polling, and task cleanup in `finally`.

## Risks / Trade-offs

- Pending cancellation is now honored by every OAuth route caller, including browser and device-start requests. Existing route and OAuth suites must cover normal/error behavior.
- The guard runs only after route-session cleanup finishes; it is not a cleanup timeout or a reversal of an already committed account write.
- Tests and validation have not been run for this assignment. Run the commands in tasks.md before landing; do not archive this change yet.

## Migration Plan

No migration or configuration change. Land only after the scoped and suite-load validation; rollback is reverting this scoped patch. No deployment is performed by this assignment.
