# Context

## Purpose

Let the upstream catalog's output budget win over the fork's hand-maintained slug table.

## Upstream provenance

Port of the `_v1_max_output_tokens` behavior exercised by upstream `13ddf3962` (#2528), whose test
`test_v1_models_prefers_raw_max_output_tokens_over_slug_fallback` is adopted. The GPT-6 128k table entries
from that commit were already in the fork. Upstream accepts any `int` (including `bool` and non-positive);
the fork accepts only positive non-bool integers.

## Decisions

- The slug table stays as the fallback because upstream catalogs do not always report the value.
- Only `_v1_max_output_tokens` changed, so every consumer (metadata, capabilities, top-level fields) agrees.

## Failure modes

- A bogus upstream value (0, negative, `true`, string) is ignored rather than advertised.

## Example

Upstream `gpt-6-sol` with `max_output_tokens=96000` is advertised as 96000; without it, 128000 from the table.
