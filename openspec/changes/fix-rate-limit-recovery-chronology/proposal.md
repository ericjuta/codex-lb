## Why

The local early-recovery path compares fresh usage against a whole-second persisted rate-limit timestamp even when the marking worker retains a more precise event time. A pre-rate-limit usage sample from the same second can therefore appear newer under slower execution and reactivate the account prematurely, causing repeat upstream attempts and sticky-session test flakiness.

## What Changes

- Require the marking worker to evaluate early-recovery usage against its precise in-memory rate-limit event timestamp.
- Preserve the persisted cooldown and peer-worker recovery rules.
- Add deterministic subsecond regression coverage while keeping the existing sticky-session retry contract unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `account-routing`: Tighten rate-limit early-recovery chronology so only usage recorded after the exact local block event can reactivate an account.

## Impact

- Affected code: account selection state derivation in `app/modules/proxy/load_balancer.py`.
- Affected tests: focused load-balancer chronology coverage; existing sticky-session integration expectations remain unchanged.
- No API, schema, migration, dependency, or configuration changes.
