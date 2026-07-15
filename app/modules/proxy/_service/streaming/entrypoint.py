from __future__ import annotations

import sys
from typing import Any, AsyncIterator, Mapping

from app.core.openai.requests import ResponsesRequest
from app.modules.api_keys.service import ApiKeyData, ApiKeyUsageReservationData
from app.modules.proxy._service.observability import _maybe_log_proxy_request_payload
from app.modules.proxy._service.streaming.protocol import _StreamingServiceProtocol

_REQUEST_TRANSPORT_HTTP = "http"


def _facade() -> Any:
    return sys.modules["app.modules.proxy.service"]


class _StreamingEntrypointMixin:
    def stream_responses(
        self: _StreamingServiceProtocol,
        payload: ResponsesRequest,
        headers: Mapping[str, str],
        *,
        codex_session_affinity: bool = False,
        propagate_http_errors: bool = False,
        openai_cache_affinity: bool = False,
        api_key: ApiKeyData | None = None,
        api_key_reservation: ApiKeyUsageReservationData | None = None,
        suppress_text_done_events: bool = False,
        request_transport: str = _REQUEST_TRANSPORT_HTTP,
        client_ip: str | None = None,
        enforce_openai_sdk_contract: bool = True,
    ) -> AsyncIterator[str]:
        proxy = self
        _maybe_log_proxy_request_payload("stream", payload, headers)
        filtered = _facade().filter_inbound_headers(headers)
        return proxy._stream_with_retry(
            payload,
            filtered,
            codex_session_affinity=codex_session_affinity,
            propagate_http_errors=propagate_http_errors,
            openai_cache_affinity=openai_cache_affinity,
            api_key=api_key,
            api_key_reservation=api_key_reservation,
            suppress_text_done_events=suppress_text_done_events,
            request_transport=request_transport,
            client_ip=client_ip,
            enforce_openai_sdk_contract=enforce_openai_sdk_contract,
        )
