## 1. Implementation

- [x] 1.1 Make `_contains_opaque_context` only classify `input_file` /
      `input_image` when the mapping's `type` value is a string, preserving
      `file_id` opacity and recursive traversal.

## 2. Tests

- [x] 2.1 Regression: `enforce_context_window` over a Responses request whose
      function-tool schema nests `{"properties": {"type": {"const":
      "preview"}}}` does not raise and still estimates/rejects normally.
- [x] 2.2 Preserve existing opaque file/image and `file_id` skip behavior.

## 3. Validation

- [x] 3.1 `uv run pytest tests/unit/test_context_window_guard.py`
- [x] 3.2 `openspec validate --specs`
