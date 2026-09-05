"""Uvicorn httptools protocol that releases keep-alive timers on every loss.

Stock uvicorn cancels the keep-alive timer only when the peer closed cleanly
(``exc is None``). After an RST / ``ECONNRESET`` the armed ``TimerHandle``
keeps the protocol — and with it the transport, request cycle and ASGI scope —
reachable from the event loop for ``--timeout-keep-alive`` seconds. This
subclass cancels the timer after the stock teardown and does not change
upgrade handling or forwarded bytes.
"""

from __future__ import annotations

from uvicorn.protocols.http.httptools_impl import HttpToolsProtocol


class KeepAliveHttpToolsProtocol(HttpToolsProtocol):
    """httptools protocol that releases the keep-alive timer on every connection loss."""

    def connection_lost(self, exc: Exception | None) -> None:
        # uvicorn (<= 0.52.4 and master) cancels the keep-alive timer only when
        # the peer closed cleanly (exc is None). Cancel it on every loss.
        # super() first: the base clears ``self.parser`` last and the cancel
        # touches only ``timeout_keep_alive_task``. The transport is not closed
        # here on the exc path (stock semantics: the loop already force-closed it).
        super().connection_lost(exc)
        self._unset_keepalive_if_required()
