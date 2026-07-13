## 1. Guard exemption

- [x] 1.1 Add terminal-`compaction_trigger` detection helper in `app/modules/proxy/request_policy.py` (shape rule identical to `strip_terminal_compaction_trigger_input`, non-mutating, non-raising)
- [x] 1.2 Early-return from `enforce_context_window` when the payload is a well-formed compaction-lane request

## 2. Regression coverage

- [x] 2.1 Unit tests: guard bypass for terminal trigger; no bypass for duplicated/non-terminal trigger; unchanged rejection for oversized non-compaction payloads
- [x] 2.2 Route-path regression test: oversized `/backend-api/codex/responses` payload with terminal `compaction_trigger` is not guard-rejected (no 400 `context_length_exceeded`)
- [x] 2.3 Websocket prepare-path regression test: oversized `response.create` payload with terminal trigger passes `enforce_context_window`

## 3. Validation

- [x] 3.1 `uv run pytest` targeted suites, then repo default suite
- [x] 3.2 `uv run ruff check`
- [x] 3.3 `openspec validate --specs` strict pass
