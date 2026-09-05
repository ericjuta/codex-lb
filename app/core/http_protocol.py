"""Uvicorn HTTP protocol selection that releases keep-alive timers on every loss.

Stock uvicorn cancels the keep-alive ``TimerHandle`` in ``connection_lost``
only when the peer closed cleanly (``exc is None``). After an RST /
``ECONNRESET`` the armed handle keeps the protocol graph reachable for
``--timeout-keep-alive`` seconds while connection accounting already reports
the connection gone. These subclasses cancel the timer after the stock
teardown and do not change upgrade handling or forwarded bytes.
"""

from __future__ import annotations

import asyncio

from uvicorn.protocols.http.h11_impl import H11Protocol


class KeepAliveH11Protocol(H11Protocol):
    """h11 protocol that releases the keep-alive timer on every connection loss."""

    def connection_lost(self, exc: Exception | None) -> None:
        # Stock h11_impl cancels the keep-alive timer only when exc is None.
        # super() first: the base sends h11.ConnectionClosed before the exc
        # check; the extra cancel touches only ``timeout_keep_alive_task``.
        super().connection_lost(exc)
        self._unset_keepalive_if_required()


def load_http_protocol_class(http: str = "auto") -> type[asyncio.Protocol]:
    """Return the HTTP protocol class for ``uvicorn.Config(http=...)``.

    Preserves uvicorn's ``auto`` / ``h11`` / ``httptools`` choices. ``auto``
    prefers the httptools subclass when httptools is importable and falls
    back to h11. Explicit ``httptools`` imports the httptools subclass and
    raises ``ImportError`` when httptools is missing.
    """

    if http not in {"auto", "h11", "httptools"}:
        raise ValueError(f"Unsupported HTTP protocol implementation: {http}")
    if http == "h11":
        return KeepAliveH11Protocol
    if http == "httptools":
        from app.core.http_protocol_httptools import KeepAliveHttpToolsProtocol

        return KeepAliveHttpToolsProtocol
    try:
        from app.core.http_protocol_httptools import KeepAliveHttpToolsProtocol
    except ImportError:
        return KeepAliveH11Protocol
    return KeepAliveHttpToolsProtocol
