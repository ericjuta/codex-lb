## 1. Catalog, Pricing, and Aliases

- [x] 1.1 Extract a shared GPT-6 raw builder and add `gpt-6-sol` and `gpt-6-luna` bootstrap metadata from the live upstream catalog.
- [x] 1.2 Share the live GPT-6 plan set across Astra, Sol, and Luna, adding `ent26` and `promax`.
- [x] 1.3 Add `gpt-6-sol` and `gpt-6-luna` pricing and aliases for standard, Priority/Fast, Flex/Batch, and long-context usage.
- [x] 1.4 Add `gpt-6-sol` and `gpt-6-luna` to request-policy suffix normalization.
- [x] 1.5 Expose the 128K output limit for Sol and Luna in OpenAI-compatible model metadata.
- [x] 1.6 Move the fallback `model_registry_client_version` default to `0.156.0`.

## 2. Tests and Validation

- [x] 2.1 Add pricing tests for Sol/Luna aliases, dated snapshots, service tiers, and long-context cost math.
- [x] 2.2 Add model-registry tests for Sol/Luna bootstrap fields, reasoning levels, shared GPT-6 plans, and websocket preference.
- [x] 2.3 Add a regression tying the fallback client version to the highest bootstrap `minimal_client_version`.
- [x] 2.4 Add request-policy tests for Sol/Luna suffix normalization and non-rewritten unsupported suffixes.
- [x] 2.5 Add OpenAI-compatible endpoint coverage for Sol/Luna output limits.
- [x] 2.6 Run OpenSpec, targeted pytest, type, and formatting validation.

## 3. Deployment

- [ ] 3.1 Deploy locally via `update.sh` and verify.
