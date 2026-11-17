## Why

The live Codex catalog now exposes `gpt-6.2-sol` and `gpt-6.2-astra` (minimum client `0.166.0`), but the fork has no bootstrap metadata, pricing, Cursor aliases or output budget for them, and its fallback client version (`0.156.0`) is older than their minimum. Several specialty models (`gpt-6-astra-law`, cyber, rosalind) and `gpt-6.1-sol` have no price rows, so their cost is unreported or priced as a different family. Ultrafast requests are billed at Fast rates although GPT-6.2 and GPT-6.1 Sol publish a higher Ultrafast rate.

## What Changes

- Add `gpt-6.2-sol` and `gpt-6.2-astra` bootstrap metadata, 128K fallback output budget, pricing and Cursor suffix aliases.
- Raise the fallback Codex client version to `0.169.0`.
- Add price rows for `gpt-6.1-sol`, `gpt-6-astra-law`, `gpt-6-cyber`, `gpt-6-rosalind`, `gpt-5.6-cyber`, `gpt-5.5-cyber`, `gpt-rosalind-discovery` and `gpt-rosalind-research`.
- Bill the `ultrafast` tier with a per-model multiplier over Standard rates when one is defined.

## Capabilities

### Modified Capabilities

- `model-catalog-compat`
- `api-keys`
- `responses-api-compat`

## Impact

No migration. `gpt-5.4` rates were compared with the upstream snapshot and already match. Out of scope: cache-write metering, `gpt-6.1-sol` bootstrap metadata.
