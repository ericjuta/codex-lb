## Why

The context-window guard's opaque-context walker crashes with `TypeError:
cannot use 'dict' as a set element` when a Responses request carries a
function-tool JSON Schema containing a nested object under a `"type"` key
(for example `{"properties": {"type": {"const": "preview"}}}`). The walker
assumes every mapping's `type` value is hashable before testing membership in
`{"input_file", "input_image"}`. This aborts websocket generation with close
code 1000 before the model is reached, blocking clients that advertise such
tool schemas (observed with the Nanocodex standalone Hashline transaction
tool).

## What Changes

- Make the opaque-context classification type-safe: only classify
  `input_file` / `input_image` from a mapping's `type` when the value is a
  string; continue treating any mapping containing `file_id` as opaque;
  continue recursive traversal for all other JSON, including schema-shaped
  objects whose `type` value is itself a mapping or list.
- Add regression coverage at the externally failing path: context-window
  enforcement over a Responses request whose tool schema nests
  `{"properties": {"type": {"const": "preview"}}}` must not raise and must
  keep estimating normally.

## Capabilities

### Modified Capabilities

- `responses-api-compat`: opaque-context detection must tolerate arbitrary
  JSON, including JSON Schema payloads where `type` maps to a non-string
  value.

## Impact

- Runtime: `app/core/openai/requests.py::_contains_opaque_context`.
- Tests: `tests/unit/test_context_window_guard.py`.
- No schema, migration, configuration, or API surface changes.
