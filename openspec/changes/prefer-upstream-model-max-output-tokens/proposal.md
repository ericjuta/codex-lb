## Why

`/v1/models` advertises `max_output_tokens` only from a fork-local slug table, so it ignores the
upstream catalog's own `max_output_tokens` and misreports models whose real budget differs from the table.

## What Changes

- Prefer the upstream model's `raw["max_output_tokens"]` when it is a positive integer.
- Fall back to the fork-local slug table when the upstream value is absent or invalid.

## Impact

- Affected spec: `model-catalog-compat`.
- Affected code: `_v1_max_output_tokens` in the proxy API.
