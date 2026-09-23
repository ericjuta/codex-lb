## Why

OpenAI's live upstream Codex catalog (`/backend-api/codex/models`, client
`0.160.0`, captured 2026-09-23) now returns `gpt-6-sol` and `gpt-6-luna`
alongside `gpt-6-astra`. codex-lb's bundled registry, pricing table, Cursor
alias normalization, and `/v1/models` max-output metadata only know Astra.

Without bootstrap entries, startup/offline paths and cost-based policy checks
can route or price Sol and Luna traffic incorrectly (or through Astra's much
higher rates) before a live account catalog refresh catches up. Upstream
Soju06/codex-lb has no GPT-6 Sol/Luna support to cherry-pick, so this change
adapts the fork's existing `gpt-6-astra` pattern plus upstream #2174's idea of
bumping the fallback Codex client version.

## What Changes

- Add `gpt-6-sol` and `gpt-6-luna` to the static bootstrap catalog with the
  fields captured from the live upstream entries, built from a shared GPT-6 raw
  builder with Astra.
- Share the live GPT-6 plan set across Astra, Sol, and Luna, which adds `ent26`
  and `promax` to Astra's bootstrap plans.
- Expose the documented 128K output limit for `gpt-6-sol` and `gpt-6-luna`
  through the OpenAI-compatible model metadata.
- Add `gpt-6-sol` and `gpt-6-luna` pricing for standard, Priority/Fast,
  Flex/Batch, and long-context requests above 272K input tokens, with aliases
  for suffixed and dated slugs that resolve to their own entries, not Astra.
- Add `gpt-6-sol` and `gpt-6-luna` to Cursor-style model-label normalization so
  reasoning and fast suffixes map to request fields.
- Move the default fallback `model_registry_client_version` from `0.153.0` to
  `0.156.0` so a degraded-startup refresh still covers the highest bootstrap
  `minimal_client_version` (`0.155.0`).

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `model-catalog-compat`: add `gpt-6-sol` and `gpt-6-luna` bootstrap entries,
  the shared GPT-6 plan set, their 128K output budget, and the fallback client
  version floor.
- `api-keys`: add `gpt-6-sol` and `gpt-6-luna` pricing and aliases for
  cost-based policy accounting.
- `responses-api-compat`: add `gpt-6-sol` and `gpt-6-luna` to supported
  GPT-family Cursor-style model aliases.

## Impact

- Affected code: `app/core/openai/model_registry.py`, `app/core/config/settings.py`,
  `app/core/usage/pricing.py`, `app/modules/proxy/api.py`,
  `app/modules/proxy/request_policy.py`.
- Affected tests: pricing, model registry bootstrap metadata, fallback client
  version, OpenAI-compatible model metadata, and request-policy alias
  normalization.
- No database schema change or user documentation change.
