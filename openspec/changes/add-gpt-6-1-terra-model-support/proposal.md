# Proposal

## Why

The live Codex catalog now exposes `gpt-6.1-terra`, but the fork lacks offline discovery, model-specific cost accounting, Cursor aliases, and output-budget metadata for it.

## What Changes

- Bundle the verified Terra Codex metadata without changing existing models.
- Expose the documented 128K output budget while preserving the Codex 500K input window.
- Add Terra pricing, dated aliases, and known Cursor reasoning/speed suffixes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `model-catalog-compat`: Terra bootstrap metadata and output budget.
- `api-keys`: Terra usage-cost accounting across existing tiers and context sizes.
- `responses-api-compat`: Terra Cursor-style model aliases.

## Impact

Registry, proxy catalog projection, pricing and request policy; existing contract tests. No migrations, dependencies, transport changes, or changes to other model pricing. Cache-write metering and new service tiers are out of scope.
