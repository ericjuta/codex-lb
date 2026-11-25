# Proposal

## Why

On 2026-11-25 upstream throttled `gpt-6.1-terra`. Terra requests failed with upstream websocket handshake `403`s, each one counted as a transient error against the serving account, and three of them put the account into a 30-second-plus backoff for every model. Only two accounts serve Terra, so both were benched together: selection returned "No available accounts" for `gpt-6.2-sol` as well, and an API key pinned to one of those accounts got `no_accounts` while its account was healthy for the model it asked for.

Transient error backoff and the connect-phase `403` cooldown are account-wide today, but the evidence they act on is about one model on one account.

## What Changes

- Transient upstream errors and the connect-phase `403` cooldown are recorded against the account and the model it was serving. Selection for another model ignores them.
- A success clears the transient count of the model that succeeded, not of other models.
- The thresholds do not change: three consecutive errors, 30 seconds doubling to 300, the backoff fallback, and the soft-drain error threshold all apply per model.
- Rate-limit, quota and permanent failures stay account-wide. A failure recorded without a model stays account-wide.
- The two health log lines name the model.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `account-routing`: transient account health is scoped to the served model.
- `responses-api-compat`: the websocket-connect `403` cooldown applies to selection for the requested model.

## Impact

Load balancer runtime state (in memory, per worker), the selection filter in `app/core/balancer/logic.py`, and the health-write call sites of the Responses stream, websocket, HTTP bridge and compact paths. No database, API schema, setting or dashboard change. No migration: the state is rebuilt from zero on restart, as it is today.
