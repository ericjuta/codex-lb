# Responses API compatibility

## ADDED Requirements

### Requirement: Responses Lite tool definitions survive input normalization

When a Responses Lite request contains an input item with `type: "additional_tools"`, the service MUST preserve that item, including its `role` and complete `tools` array, in the upstream request payload. Instruction normalization MUST NOT move it into top-level `instructions` or drop it because it has no textual content.

#### Scenario: Codex Code Mode tools reach upstream

- **WHEN** a Codex client sends a Responses Lite request whose input contains a developer `additional_tools` item with `exec` and `wait` definitions
- **THEN** the normalized upstream payload contains the same `additional_tools` item
- **AND** the item retains the complete `exec` and `wait` tool definitions
- **AND** ordinary textual system and developer messages continue to merge into top-level `instructions`

#### Scenario: Tool definitions are not mistaken for developer instructions

- **WHEN** an `additional_tools` item has no textual content
- **THEN** it is not removed as an empty developer instruction item
- **AND** it remains in its original position relative to the other input items
