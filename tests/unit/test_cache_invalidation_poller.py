from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache.invalidation import NAMESPACE_API_KEY, NAMESPACE_FIREWALL, CacheInvalidationPoller

pytestmark = pytest.mark.unit


def _poller() -> CacheInvalidationPoller:
    return CacheInvalidationPoller(lambda: cast(AsyncSession, None))


async def test_persistent_failure_keeps_one_pending_entry_per_namespace(monkeypatch) -> None:
    poller = _poller()
    write = AsyncMock(side_effect=RuntimeError("database down"))
    monkeypatch.setattr(poller, "_write_bump", write)

    for _ in range(5):
        await poller.bump(NAMESPACE_API_KEY)
        await poller._flush_pending_bumps()
    await poller.bump(NAMESPACE_FIREWALL)

    assert poller._pending_bumps == {NAMESPACE_API_KEY, NAMESPACE_FIREWALL}

    write.side_effect = None
    await poller._flush_pending_bumps()
    assert poller._pending_bumps == set()


@pytest.mark.parametrize("path", ["direct", "flush"])
async def test_cancelled_bump_is_retained_and_cancellation_propagates(monkeypatch, path: str) -> None:
    poller = _poller()
    started = asyncio.Event()

    async def parked_write(_namespace: str) -> None:
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(poller, "_write_bump", parked_write)
    if path == "flush":
        poller._pending_bumps.add(NAMESPACE_API_KEY)
    task = asyncio.create_task(poller.bump(NAMESPACE_API_KEY) if path == "direct" else poller._flush_pending_bumps())
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert poller._pending_bumps == {NAMESPACE_API_KEY}


async def test_failure_during_another_in_flight_write_survives_its_success(monkeypatch) -> None:
    poller = _poller()
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def write(_namespace: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await release.wait()
            return
        raise RuntimeError("second write failed")

    monkeypatch.setattr(poller, "_write_bump", write)
    first = asyncio.create_task(poller.bump(NAMESPACE_API_KEY))
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        await poller.bump(NAMESPACE_API_KEY)
        release.set()
        await asyncio.wait_for(first, timeout=2)
    finally:
        if not first.done():
            first.cancel()
        await asyncio.gather(first, return_exceptions=True)

    assert poller._pending_bumps == {NAMESPACE_API_KEY}
