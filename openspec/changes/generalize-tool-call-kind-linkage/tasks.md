# Tasks

- [x] 1.1 Generalize `_has_buffered_client_tool_calls`
      (`app/core/clients/codex_continuation.py`, shared by the ws fold) to
      also match any buffered item carrying a non-empty `call_id`.
- [x] 1.2 Generalize `_missing_tool_output_variant`
      (`app/modules/proxy/service.py`) to match both linkage message frames
      for any call kind.
- [x] 1.3 Unit tests: `tool_search_call` message variants classify;
      fold stops on a buffered `tool_search_call` (call_id present, type
      outside the enumerated set).
- [x] 1.4 ruff + targeted pytest + `openspec validate
      generalize-tool-call-kind-linkage --strict`.
