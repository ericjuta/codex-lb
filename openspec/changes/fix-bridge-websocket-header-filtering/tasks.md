# Tasks

- [x] Base `_WEBSOCKET_HOP_BY_HOP_HEADERS` in `app/core/clients/proxy_websocket.py`
      on `_WEBSOCKET_EXCLUDED_HEADER_NAMES` so `accept` and `content-type` are
      excluded from upstream websocket handshake headers again.
- [x] Confirm the existing regression tests
      `tests/unit/test_proxy_http_bridge.py::test_create_http_bridge_session_filters_http_headers_for_upstream_websocket`
      and
      `tests/unit/test_proxy_http_bridge.py::test_reconnect_http_bridge_session_filters_http_headers_for_upstream_websocket`
      pass unchanged.
- [x] Run the websocket proxy unit and integration suites plus the full test
      suite; validate the OpenSpec change strictly.
