## ADDED Requirements

### Requirement: Codex compaction outputs preserve upstream item identity

When Codex-affinity compaction selects an upstream compaction output item with opaque `encrypted_content` and a non-empty string `id`, the proxy MUST preserve that exact `id` with the encrypted content in the normalized compaction item. The proxy MUST NOT invent or replace a compaction item ID. The preserved normalized item MUST be identical across the direct Codex compact JSON response and both compaction item locations in a terminal-trigger SSE response. Public OpenAI-style compact behavior MUST remain unchanged.

#### Scenario: Direct Codex compact response preserves the upstream ID

- **WHEN** `POST /backend-api/codex/responses/compact` receives an upstream compact result containing a compaction item with a non-empty string `id` and `encrypted_content`
- **THEN** the normalized single output item contains that exact `id` and encrypted content
- **AND** the proxy does not synthesize a replacement ID

#### Scenario: Terminal compaction trigger streams the preserved ID

- **WHEN** `POST /backend-api/codex/responses` ends with one valid `compaction_trigger` and upstream compact output includes a non-empty compaction item `id`
- **THEN** `response.output_item.done.item` contains the exact upstream `id`
- **AND** `response.completed.response.output` contains the same normalized item

#### Scenario: Missing upstream ID remains missing

- **WHEN** the selected upstream compaction result contains encrypted content without a non-empty string `id`
- **THEN** the normalized compaction item omits `id`
- **AND** the proxy does not invent one
