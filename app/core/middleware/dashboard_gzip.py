from __future__ import annotations

from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

# Only bounded dashboard API responses are compressed. Static FileResponse
# bodies stream gzip without a content length, which some reverse proxies
# terminate before forwarding the body. Proxy paths (/backend-api, /v1,
# websockets) also stream and must never pass through this wrapper.
_COMPRESSED_PATH_PREFIXES = ("/api/",)


class DashboardGZipMiddleware:
    """Apply gzip to bounded dashboard API responses only."""

    def __init__(self, app: ASGIApp, minimum_size: int = 1024) -> None:
        self._plain = app
        self._gzip = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope.get("path", "").startswith(_COMPRESSED_PATH_PREFIXES)
            and not _has_range_header(scope)
        ):
            await self._gzip(scope, receive, send)
            return
        await self._plain(scope, receive, send)


def _has_range_header(scope: Scope) -> bool:
    """Ranged requests bypass gzip: FileResponse builds the 206 and its
    Content-Range against the uncompressed file, so compressing the body
    afterwards would describe offsets the encoded bytes no longer match.
    Header-name casing is normalized because not every ASGI server
    lowercases request header names."""
    return any(name.lower() == b"range" for name, _ in scope.get("headers", ()))


def add_dashboard_gzip_middleware(app) -> None:
    app.add_middleware(DashboardGZipMiddleware)
