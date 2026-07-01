# Change: fix bridge websocket upstream header filtering

## Why

Commit `ce9b12ab` narrowed `_HOP_BY_HOP_HEADER_NAMES` in
`app/core/clients/proxy.py` (removing `accept` and `content-type` so plain
HTTP proxying keeps forwarding them) and introduced
`_WEBSOCKET_EXCLUDED_HEADER_NAMES` for the websocket egress built inside
`proxy.py`. The websocket client module `app/core/clients/proxy_websocket.py`
still composes its own exclusion set from the narrowed
`_HOP_BY_HOP_HEADER_NAMES`, so `filter_inbound_websocket_headers` — used by
the HTTP responses bridge when opening upstream websocket sessions — forwards
downstream `accept: text/event-stream` and `content-type: application/json`
headers onto the upstream websocket handshake. At the upstream merge-base
(`f212300d`) these headers were excluded; the regression tests
`tests/unit/test_proxy_http_bridge.py::test_create_http_bridge_session_filters_http_headers_for_upstream_websocket`
and
`tests/unit/test_proxy_http_bridge.py::test_reconnect_http_bridge_session_filters_http_headers_for_upstream_websocket`
still encode that contract and fail on current `main`.

## What Changes

- Compose the websocket client's exclusion set from
  `_WEBSOCKET_EXCLUDED_HEADER_NAMES` (single source of truth) instead of the
  narrowed `_HOP_BY_HOP_HEADER_NAMES`, restoring the `accept` and
  `content-type` exclusion on every upstream websocket handshake built from
  inbound HTTP headers (bridge create and bridge reconnect included).
- No change to plain HTTP proxy header forwarding.

## Impact

Upstream websocket handshakes opened on behalf of HTTP bridge clients no
longer leak HTTP content-negotiation headers that do not describe the
websocket protocol exchange. Existing regression tests at the bridge session
create and reconnect paths go green without being edited.
