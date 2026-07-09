# Preserve Responses Lite tool definitions through request normalization

## Problem

Codex Responses Lite requests carry client-executable tool definitions in an input item with `type: "additional_tools"` and `role: "developer"`. The proxy currently treats every developer item as ordinary instructions, moves textual content into `instructions`, and drops items without textual content. That removes the `exec` and `wait` definitions before the request reaches upstream, so GPT-5.6 Code Mode models can only emit tool-shaped text instead of invoking tools.

## What Changes

- Preserve `additional_tools` input items byte-for-byte during instruction normalization.
- Keep ordinary system/developer message behavior unchanged.
- Add a regression test for the Responses Lite tool-definition shape.
- Document the request-body compatibility contract in OpenSpec.

## Capabilities

### Modified Capabilities

- `responses-api-compat`: preserve Responses Lite client-executable tool definitions.

## Impact

- Affects `app/core/openai/requests.py` input normalization.
- Adds focused unit coverage in `tests/unit/test_openai_requests.py`.
- Does not change header filtering, routing, authentication, or upstream response handling.
