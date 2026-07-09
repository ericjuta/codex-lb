## 1. Proxy Behavior

- [x] 1.1 Remove the Responses Lite header from the shared inbound header blocklist.
- [x] 1.2 Preserve all unrelated authentication, proxy identity, and hop-by-hop filtering behavior.
- [x] 1.3 Forward the exact Responses Lite header through the compact minimal-header builder without broadening compact header passthrough.

## 2. Bootstrap Model Metadata

- [x] 2.1 Add the GPT-5.6 Sol, Terra, and Luna Lite, Code Mode, experimental-tool, and multi-agent metadata to the static fallback catalog.
- [x] 2.2 Preserve the same capability metadata in the Codex model endpoint serialization.

## 3. Regression Coverage

- [x] 3.1 Update shared and HTTP upstream header tests to require Responses Lite passthrough.
- [x] 3.2 Update internal and client-facing WebSocket header tests to require Responses Lite passthrough.
- [x] 3.3 Add compact-header regression coverage for Lite passthrough and unrelated-header filtering.
- [x] 3.4 Add bootstrap model endpoint regression coverage for GPT-5.6 capability metadata.

## 4. Validation

- [x] 4.1 Run focused proxy, model-registry, and Codex model-manager regression tests.
- [x] 4.2 Run strict OpenSpec validation and review the final diff.
