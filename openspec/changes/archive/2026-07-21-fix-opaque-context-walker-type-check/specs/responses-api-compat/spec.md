## ADDED Requirements

### Requirement: Opaque-context detection tolerates arbitrary JSON

When deciding whether a Responses request contains opaque context that prevents local input estimation, the proxy MUST classify a mapping as an opaque `input_file` or `input_image` content item only when the mapping's `type` value is a string equal to one of those identifiers. A mapping containing a `file_id` key MUST still be treated as opaque. All other JSON values, including JSON Schema fragments where a `type` key maps to an object or array (for example `{"properties": {"type": {"const": "preview"}}}`), MUST be traversed recursively without raising an error.

#### Scenario: Tool schema with object-valued type key does not crash the guard

- **GIVEN** a Responses request whose function-tool JSON Schema contains
  `{"properties": {"type": {"const": "preview"}}}`
- **WHEN** context-window enforcement estimates the request
- **THEN** estimation completes without error
- **AND** the schema fragment is not classified as opaque context

#### Scenario: Opaque file and image items still skip estimation

- **GIVEN** a Responses request containing an `input_file` or `input_image`
  content item, or any mapping with a `file_id` key
- **WHEN** the proxy attempts local input estimation
- **THEN** the request is treated as opaque and preserved on the existing
  upstream handling path
