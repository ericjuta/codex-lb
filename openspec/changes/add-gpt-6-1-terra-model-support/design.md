# Design

## Context

The 2026-10-27 live Codex catalog contains Terra; fetched upstream main `72630bbfe` has no bootstrap entry, and the upstream metadata branch has no Terra price entry. See proposal.md for scope.

## Goals / Non-Goals

Reuse the existing registry, price table and suffix resolver. No migrations, transport changes, new service tiers, cache-write accounting, or unrelated model updates.

## Decisions

- Use Codex metadata for the Codex proxy: 500K input context and low default reasoning. The public API model documentation reports different context/reasoning defaults; these must not overwrite observed Codex metadata.
- Reuse the shared GPT-6 raw builder, with Terra-only raw overrides and plan additions. Leave existing models untouched.
- Use the documented 128K output budget in the existing compatibility override table; upstream output metadata continues to win.
- Keep client version 0.156.0: it already exceeds Terra's minimum 0.153.0.
- Price Terra with the existing long-context engine. Its cached input is 5% of uncached input, not the 10% used by older GPT-6 entries.

## Risks / Trade-offs

Bootstrap metadata is a dated fallback, not a replacement for refresh. Pricing comes from the API rate card and remains an estimate for subscription-backed usage. Advertising a model does not prove every account is entitled to run it.
