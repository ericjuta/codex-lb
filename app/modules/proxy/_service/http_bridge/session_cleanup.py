from __future__ import annotations

import asyncio
import logging

from app.modules.proxy._service.http_bridge.helpers import (
    _HTTP_BRIDGE_BACKGROUND_CLOSE_TIMEOUT_SECONDS,
    _close_http_bridge_session_bounded,
)
from app.modules.proxy._service.http_bridge.protocol import _HTTPBridgeServiceProtocol
from app.modules.proxy._service.observability import _hash_identifier
from app.modules.proxy._service.support import _HTTPBridgeSession

logger = logging.getLogger("app.modules.proxy.service")
_HTTP_BRIDGE_BACKGROUND_CLEANUP_WARN_THRESHOLD = 100


class _HTTPBridgeSessionCleanupMixin:
    async def _close_http_bridge_session_bounded(
        self: _HTTPBridgeServiceProtocol,
        session: _HTTPBridgeSession,
        *,
        reason: str,
    ) -> None:
        await _close_http_bridge_session_bounded(self, session, reason=reason)

    def _schedule_http_bridge_session_closes(
        self: _HTTPBridgeServiceProtocol,
        sessions: list[_HTTPBridgeSession],
        *,
        reason: str,
    ) -> None:
        for session in sessions:
            if len(self._background_cleanup_tasks) >= _HTTP_BRIDGE_BACKGROUND_CLEANUP_WARN_THRESHOLD:
                logger.warning(
                    "http_bridge_background_cleanup_backlog action=session_close count=%d threshold=%d reason=%s",
                    len(self._background_cleanup_tasks),
                    _HTTP_BRIDGE_BACKGROUND_CLEANUP_WARN_THRESHOLD,
                    reason,
                )
            self._schedule_cancel_safe_cleanup(
                self._close_http_bridge_session_bounded(session, reason=reason),
                action="http_bridge_session_close",
                request_id=_hash_identifier(session.key.affinity_key),
            )

    async def _drain_http_bridge_background_cleanup_tasks(
        self: _HTTPBridgeServiceProtocol,
        *,
        reason: str,
    ) -> None:
        tasks = [
            task
            for task in self._background_cleanup_tasks
            if not task.done()
            and (
                task.get_name().startswith("proxy-http_bridge_session_close-")
                or task.get_name().startswith("http-bridge-close-")
            )
        ]
        if not tasks:
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(*(asyncio.shield(task) for task in tasks), return_exceptions=True),
                timeout=_HTTP_BRIDGE_BACKGROUND_CLOSE_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning(
                "http_bridge_background_cleanup_drain_timeout reason=%s count=%d timeout_seconds=%.1f",
                reason,
                len(tasks),
                _HTTP_BRIDGE_BACKGROUND_CLOSE_TIMEOUT_SECONDS,
            )
