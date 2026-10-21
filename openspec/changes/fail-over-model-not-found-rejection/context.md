# Context

## Purpose

Keep a model-level rejection from damaging account health and let another account answer it.

## Upstream provenance

Reimplementation of the open WIP `origin/fix/model-not-found-failover` (upstream PR #2332). Skipped: its
`model_rejection_replay_count` / `completed_forced_refresh_account_id` bookkeeping and `owner_bound` failover
decision argument. The fork reuses the existing one-shot account/model replay (support.py / websocket mixin),
which already preserves the original envelope and honors file/continuity pins.

## Decisions

- Only the exact code is matched; the legacy message-only entitlement rejection is unchanged.
- WebSocket replay is carried by the shared predicate; no new replay state was added. The native WebSocket path has a
  regression (parametrized stale-account test); the HTTP bridge shares the predicate but has no new test [INFERENCE: it follows the same code].

## Failure modes

- Every account lacking the model: the second rejection surfaces the original 404.

## Example

Account A: 404 `model_not_found`; account B serves; A remains ACTIVE with zero recorded errors.
