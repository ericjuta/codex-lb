from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache.invalidation import NAMESPACE_API_KEY, NAMESPACE_FIREWALL, CacheInvalidationPoller
from app.db.session import SessionLocal

pytestmark = pytest.mark.integration


def _flaky_session_factory(failures: int) -> tuple[Callable[[], AsyncSession], list[int]]:
    """Session factory whose first ``failures`` sessions cannot reach the database."""
    created = [0]

    def factory() -> AsyncSession:
        created[0] += 1
        if created[0] <= failures:
            raise ConnectionError("database unavailable")
        return SessionLocal()

    return factory, created


def _peer(namespace: str) -> tuple[CacheInvalidationPoller, list[str]]:
    seen: list[str] = []
    peer = CacheInvalidationPoller(SessionLocal)
    peer.on_invalidation(namespace, lambda: seen.append(namespace))
    return peer, seen


async def test_failed_bump_is_republished_on_next_poll_and_peer_observes(db_setup) -> None:
    factory, _ = _flaky_session_factory(failures=1)
    writer = CacheInvalidationPoller(factory)
    peer, seen = _peer(NAMESPACE_API_KEY)
    await peer._poll_once()  # prime the peer before any version exists

    await writer.bump(NAMESPACE_API_KEY)  # key mutation committed, but the publish failed
    await peer._poll_once()
    assert seen == []  # peer is stale: this is the bug being fixed

    await writer._flush_pending_bumps()  # what the writer's next poll tick runs
    await peer._poll_once()

    assert seen == [NAMESPACE_API_KEY]
    assert writer._pending_bumps == set()


async def test_running_poll_loop_retries_a_failed_bump_until_peer_observes(db_setup) -> None:
    factory, created = _flaky_session_factory(failures=3)
    writer = CacheInvalidationPoller(factory, poll_interval_seconds=0.01)
    peer, seen = _peer(NAMESPACE_FIREWALL)
    await peer._poll_once()

    await writer.start()
    try:
        await writer.bump(NAMESPACE_FIREWALL)
        async with asyncio.timeout(5):
            while writer._pending_bumps:
                await asyncio.sleep(0.01)
    finally:
        await writer.stop()
    await peer._poll_once()

    assert seen == [NAMESPACE_FIREWALL]
    assert created[0] == 4  # three failed attempts, then one successful publish


async def test_successful_bump_leaves_nothing_to_retry(db_setup) -> None:
    writer = CacheInvalidationPoller(SessionLocal)
    peer, seen = _peer(NAMESPACE_API_KEY)
    await peer._poll_once()

    await writer.bump(NAMESPACE_API_KEY)
    await writer._flush_pending_bumps()
    await peer._poll_once()
    await peer._poll_once()

    assert writer._pending_bumps == set()
    assert seen == [NAMESPACE_API_KEY]  # exactly one version bump reached the peer
