## Context

`gpt-6-sol` and `gpt-6-luna` are present in the live upstream Codex model
catalog captured on 2026-09-23 with client version `0.160.0`. codex-lb already
bootstraps `gpt-6-astra` from a captured entry and owns pricing, catalog
metadata, `/v1/models` output-budget overrides, and Cursor-style label
normalization in separate modules. Upstream Soju06/codex-lb has no Sol/Luna
support, so this change extends the fork's Astra pattern.

## Goals / Non-Goals

**Goals:**

- Teach bootstrap model discovery about `gpt-6-sol` and `gpt-6-luna` with the
  captured upstream metadata.
- Keep every GPT-6 bootstrap entry on the plan set the live catalog advertises.
- Expose the documented 128K output limit through the OpenAI-compatible model
  projection.
- Price Sol and Luna requests with their own published rates across standard,
  Priority/Fast, Flex/Batch, and long-context paths.
- Normalize known suffix labels for Sol and Luna through the existing
  request-policy path.
- Keep the fallback Codex client version at or above the highest bootstrap
  `minimal_client_version`.

**Non-Goals:**

- Add a cache-write pricing field; current `ModelPrice` cannot represent it.
- Change account import, database schema, or upstream refresh behavior.
- Add `max` or `ultra` model-name suffix tokens to Cursor alias normalization.
- Re-point the bare `gpt-6` pricing alias away from `gpt-6-astra`.

## Decisions

- Build Astra, Sol, and Luna from one shared GPT-6 raw builder. The live
  entries differ only in display name, description, priority, minimal client
  version, reasoning levels, service-tier text, default service tier,
  `multi_agent_reasoning_effort`, and `node_repl_auto_review_required`; a
  single builder keeps the common upstream fields from drifting.
- Sol advertises the `ultra` reasoning level (`low` through `ultra`); Luna stops
  at `max`. This matches the live catalog exactly.
- Sol and Luna keep `default_service_tier` `null` and the `priority` tier named
  `Fast` with description `1.5x speed`, as the live catalog does. Astra keeps
  its own captured `priority` default and `2x speed, increased usage` text.
- All three GPT-6 entries use the live GPT-6 plan set, which adds `ent26` and
  `promax` to Astra.
- Prices come from the OpenAI API pricing page as read on 2026-09-23. Each tier
  uses explicit per-tier `ModelPrice` values with the same `272000` input-token
  long-context threshold as Astra instead of model-name conditionals.
- Suffixed and dated slugs (`gpt-6-sol*`, `gpt-6-luna*`) alias to their own
  canonical entries. Alias ordering MUST keep them from falling through to the
  `gpt-6-astra` or bare `gpt-6` entries.
- The 128K output limit lives in the existing bounded compatibility override
  table; the Codex-native catalog remains unchanged.
- Fallback client version moves to `0.156.0` (current `@openai/codex` npm
  release), following upstream #2174's approach of bumping the fallback so it
  covers every bootstrap `minimal_client_version`.
- The live model registry remains authoritative; bootstrap entries are only the
  startup/offline floor.

## Risks / Trade-offs

- [Risk] Upstream may later change Sol/Luna text or tiers. -> The live refresh
  remains authoritative and replaces bootstrap metadata once available.
- [Risk] Pricing may change after 2026-09-23. -> Rates are explicit per model
  and tier, so a later correction touches one table entry.
- [Risk] A future `@openai/codex` release could raise minimal client versions
  beyond `0.156.0`. -> A regression test ties the fallback version to the
  highest bootstrap `minimal_client_version`.
