from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CacheInvalidation
from app.db.session import close_session

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

NAMESPACE_API_KEY = "api_key"
NAMESPACE_FIREWALL = "firewall"
type InvalidationCallback = Callable[[], None | Awaitable[None]]


class CacheInvalidationPoller:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        poll_interval_seconds: float = 0.5,
    ) -> None:
        self._session_factory = session_factory
        self._poll_interval = poll_interval_seconds
        self._known_versions: dict[str, int] = {}
        self._callbacks: dict[str, list[InvalidationCallback]] = {}
        self._poll_initialized = False
        # Namespaces whose immediate publish failed or was interrupted; bounded
        # by the fixed namespace set and re-published by the poll loop.
        self._pending_bumps: set[str] = set()
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    def on_invalidation(self, namespace: str, callback: InvalidationCallback) -> None:
        self._callbacks.setdefault(namespace, []).append(callback)

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def bump(self, namespace: str) -> None:
        """Publish now; retain the namespace for the next poll if the write does not complete.

        The pending marker is consumed before the write so a bump requested while
        this write is in flight re-queues instead of coalescing into it. An
        interrupted write may already have committed; a redundant version bump
        only re-runs peers' idempotent callbacks, while losing one leaves peers stale.
        """
        already_pending = namespace in self._pending_bumps
        self._pending_bumps.discard(namespace)
        published = False
        try:
            await self._write_bump(namespace)
            published = True
        except Exception:
            logger.log(
                logging.DEBUG if already_pending else logging.WARNING,
                "cache_invalidation bump failed for namespace %s; retrying on next poll",
                namespace,
                exc_info=True,
            )
        finally:
            # Also covers cancellation, which still propagates to the caller.
            if not published:
                self._pending_bumps.add(namespace)

    async def _write_bump(self, namespace: str) -> None:
        session = self._session_factory()
        try:
            dialect = session.get_bind().dialect.name
            if dialect == "postgresql":
                stmt = (
                    pg_insert(CacheInvalidation)
                    .values(namespace=namespace, version=1)
                    .on_conflict_do_update(
                        index_elements=[CacheInvalidation.namespace],
                        set_={"version": CacheInvalidation.version + 1},
                    )
                )
                await session.execute(stmt)
            elif dialect == "sqlite":
                stmt = (
                    sqlite_insert(CacheInvalidation)
                    .values(namespace=namespace, version=1)
                    .on_conflict_do_update(
                        index_elements=[CacheInvalidation.namespace],
                        set_={"version": CacheInvalidation.version + 1},
                    )
                )
                await session.execute(stmt)
            else:
                existing = await session.scalar(
                    select(CacheInvalidation).where(CacheInvalidation.namespace == namespace)
                )
                if existing is None:
                    session.add(CacheInvalidation(namespace=namespace, version=1))
                else:
                    await session.execute(
                        update(CacheInvalidation)
                        .where(CacheInvalidation.namespace == namespace)
                        .values(version=CacheInvalidation.version + 1)
                    )
            await session.commit()
        finally:
            await close_session(session)

    async def _flush_pending_bumps(self) -> None:
        # bump() never raises Exception and re-queues on cancellation itself.
        for namespace in sorted(self._pending_bumps):
            await self.bump(namespace)

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._flush_pending_bumps()
                await self._poll_once()
            except Exception:
                logger.debug("cache_invalidation poll failed", exc_info=True)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll_interval)
            except asyncio.TimeoutError:
                continue

    async def _poll_once(self) -> None:
        session = self._session_factory()
        try:
            result = await session.execute(select(CacheInvalidation.namespace, CacheInvalidation.version))
            rows = result.all()
        except Exception:
            return
        finally:
            await close_session(session)

        for namespace, version in rows:
            prev = self._known_versions.get(namespace)
            if prev is not None and version != prev:
                for cb in self._callbacks.get(namespace, []):
                    try:
                        result = cb()
                        if isawaitable(result):
                            await result
                    except Exception:
                        logger.debug("cache_invalidation callback error", exc_info=True)
            elif prev is None and self._poll_initialized and version > 0:
                for cb in self._callbacks.get(namespace, []):
                    try:
                        result = cb()
                        if isawaitable(result):
                            await result
                    except Exception:
                        logger.debug("cache_invalidation callback error", exc_info=True)
            self._known_versions[namespace] = version
        self._poll_initialized = True


_poller: CacheInvalidationPoller | None = None


def get_cache_invalidation_poller() -> CacheInvalidationPoller | None:
    return _poller


def set_cache_invalidation_poller(poller: CacheInvalidationPoller) -> None:
    global _poller
    _poller = poller
