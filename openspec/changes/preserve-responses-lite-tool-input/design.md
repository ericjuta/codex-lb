# Design

`_normalize_responses_input_instructions` will recognize the Responses API `additional_tools` item before inspecting its role. It will append that item unchanged to the normalized input list and will not mark the input as changed for that item. Text-bearing `system` and `developer` message items continue to merge into top-level `instructions`, while non-text message content continues to be preserved as user input.

The special case is deliberately limited to `type == "additional_tools"`; it does not broaden preservation for arbitrary developer control items. The existing downstream sanitization and payload serialization then forward the tool definitions without reconstructing or filtering their schemas.

The regression test will validate both the parsed request and `to_payload()` output, including the `exec` and `wait` definitions, so it covers the externally forwarded request contract rather than only the helper implementation.
