## Why

The warmup path still defaults to `gpt-5.4-mini`, while the bundled model catalog already supports `gpt-5.6-luna`. Aligning the warmup default with that supported model makes new and otherwise-unconfigured warmup executions use the requested model.

## What Changes

- Change the application and example environment warmup default to `gpt-5.6-luna`.
- Change the dashboard-settings default used for newly created settings rows to `gpt-5.6-luna`.
- Make quota-planner warm-now fallback use the shared warmup default instead of a duplicated model literal.
- Update focused API and configuration regression expectations.
- Preserve explicitly configured dashboard and quota-planner model preferences.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `quota-phase-planner`: the default model for warmup execution when no explicit planner preference is set becomes `gpt-5.6-luna`.

## Impact

- Affected application settings, dashboard settings model defaults, quota-planner warmup execution, example configuration, tests, and OpenSpec requirements.
- No new dependency or API shape is introduced.
- Existing persisted operator-selected warmup values are not overwritten by this default change.
