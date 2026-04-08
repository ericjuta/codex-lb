from __future__ import annotations

import logging
from asyncio import Semaphore
from dataclasses import dataclass

from app.core.clients.proxy import ProxyResponseError
from app.core.resilience.overload import local_overload_error
from app.core.utils.request_id import get_request_id

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AdmissionLease:
    _semaphore: Semaphore | None
    _released: bool = False

    def release(self) -> None:
        if self._released or self._semaphore is None:
            return
        self._released = True
        self._semaphore.release()


class WorkAdmissionController:
    def __init__(
        self,
        *,
        token_refresh_limit: int,
        websocket_connect_limit: int,
        response_create_limit: int,
        compact_response_create_limit: int,
    ) -> None:
        self._token_refresh = Semaphore(token_refresh_limit) if token_refresh_limit > 0 else None
        self._websocket_connect = Semaphore(websocket_connect_limit) if websocket_connect_limit > 0 else None
        self._response_create = Semaphore(response_create_limit) if response_create_limit > 0 else None
        self._compact_response_create = (
            Semaphore(compact_response_create_limit) if compact_response_create_limit > 0 else None
        )

    async def acquire_token_refresh(self) -> AdmissionLease:
        return await self._acquire(self._token_refresh, stage="token_refresh")

    async def acquire_websocket_connect(self) -> AdmissionLease:
        return await self._acquire(self._websocket_connect, stage="upstream_websocket_connect")

    async def acquire_response_create(self, *, compact: bool = False) -> AdmissionLease:
        semaphore = self._compact_response_create if compact else self._response_create
        stage = "compact_response_create" if compact else "response_create"
        return await self._acquire(semaphore, stage=stage)

    async def _acquire(self, semaphore: Semaphore | None, *, stage: str) -> AdmissionLease:
        if semaphore is None:
            return AdmissionLease(None)
        if semaphore.locked():
            message = f"codex-lb is temporarily overloaded during {stage}"
            logger.warning(
                "proxy_admission_rejected request_id=%s stage=%s status=429 available=%s message=%s",
                get_request_id(),
                stage,
                0,
                message,
            )
            raise ProxyResponseError(429, local_overload_error(message))
        await semaphore.acquire()
        return AdmissionLease(semaphore)
