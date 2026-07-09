# Tasks

## Specification

- [x] T1: Add the Responses Lite `additional_tools` preservation requirement and scenarios.

## Implementation

- [x] T2: Preserve `type: "additional_tools"` input items in `app/core/openai/requests.py` before developer-message normalization.

## Tests

- [x] T3: Add a unit regression test covering `exec` and `wait` tool definitions in `tests/unit/test_openai_requests.py`.

## Validation

- [x] T4: Run the focused request-model tests.
- [x] T5: Run strict OpenSpec validation.
- [x] T6: Rebuild/restart codex-lb and verify a built Codex CLI with `model_provider="codex-lb"` creates an external marker through the model-visible `exec` tool.
