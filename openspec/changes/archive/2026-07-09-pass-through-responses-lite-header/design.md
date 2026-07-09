## Context

The shared inbound header filter currently classifies `x-openai-internal-codex-responses-lite` as an internal upstream header and removes it. Both HTTP and WebSocket upstream builders invoke that filter, so the client opt-in never reaches OpenAI.

## Goals / Non-Goals

**Goals:**

- Preserve the Responses Lite header through every supported Responses and compact transport.
- Keep static GPT-5.6 model discovery aligned with Codex's Lite and Code Mode capabilities.
- Keep all existing proxy identity, hop-by-hop, and authentication header filtering unchanged.
- Prove passthrough with focused HTTP and WebSocket regression tests.

**Non-Goals:**

- Determine which upstream models support Responses Lite.
- Rewrite Responses request bodies or alter routing, quota, authentication, or retry behavior.
- Convert upstream compatibility errors into proxy-specific responses.

## Decisions

Remove the Responses Lite header from the explicit internal-header blocklist while retaining the shared filtering calls in all upstream builders. This is narrower than bypassing `filter_inbound_headers()`, which would reintroduce forwarding of credentials, proxy identity headers, and transport metadata.

The compact builder keeps its WAF-safe minimal header set and forwards only the exact Responses Lite header from the inbound mapping. This preserves the client-selected mode without broadly forwarding compact-request headers.

The static GPT-5.6 Sol and Terra entries advertise `use_responses_lite=true`, `tool_mode=code_mode_only`, `experimental_supported_tools=["exec", "wait"]`, and `multi_agent_version=v2`. Luna uses the same capability fields with `multi_agent_version=v1`. These fields are emitted as raw model metadata by the Codex model endpoint and are used only until the live upstream catalog is available.

Tests will assert that the original header name and value survive filtering and each direct upstream builder. This establishes passthrough without coupling tests to upstream service availability.

## Risks / Trade-offs

- [Unsupported upstream models can reject Lite requests] -> Preserve the upstream error so the client receives the actual compatibility result; clients that do not send the header are unaffected.
- [An internal upstream contract may change] -> Scope passthrough to the exact existing header and retain all other filtering policies.
- [The static catalog can drift from the live catalog] -> Keep the fallback fields covered by endpoint regression tests and let a successful live refresh remain authoritative.
