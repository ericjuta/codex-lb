"""Regression tests for the 2026-08-30 shield-callback event-loop livelock.

Python 3.14's ``asyncio.shield`` leaves callbacks behind on a still-pending
inner task whenever the outer await is cancelled (``_clear_awaited_by_callback``
is never detached), and every later detach pays an O(n) scan of the inner
task's callback list. The http-bridge copy of
``_await_task_deferring_cancellation`` re-shielded its task in a bare
``while True`` loop, so a level-cancelled Starlette scope (client disconnect)
busy-spun the loop against any slow cleanup task — production autopsy found
cleanup tasks carrying 100k+ leaked callbacks and the event loop starved at
~50% of GIL samples inside ``Future.remove_done_callback``.

The structural invariant under test: no matter how often a waiter is
cancelled — edge ``task.cancel()`` or a level-cancelled anyio scope — the
awaited task's callback list stays bounded, while the defer-cancellation
semantics (finish the owned task, then surface the caller's cancellation)
are preserved.
"""

from __future__ import annotations

import asyncio

import anyio
import pytest

from app.core.utils.shared_future import wait_on_shared_future
from app.core.utils.sse import inject_sse_keepalives
from app.modules.proxy._service.http_bridge.helpers import (
    _await_task_deferring_cancellation,
)

pytestmark = pytest.mark.unit


def _callback_count(future: asyncio.Future) -> int:
    return len(getattr(future, "_callbacks", None) or [])


async def test_level_cancelled_scope_does_not_grow_task_callbacks():
    """A cancelled anyio scope must not spin-leak callbacks onto the task."""

    release = asyncio.Event()

    async def cleanup() -> str:
        await release.wait()
        return "settled"

    task = asyncio.create_task(cleanup())
    await asyncio.sleep(0)

    async def waiter() -> tuple[str, asyncio.CancelledError | None]:
        with anyio.CancelScope() as scope:
            scope.cancel()
            return await _await_task_deferring_cancellation(task)

    waiter_task = asyncio.create_task(waiter())
    # Give the old busy-spin ample iterations to manifest: the unshielded
    # loop leaked >900 callbacks in 50ms of wall clock.
    await asyncio.sleep(0.05)
    assert _callback_count(task) <= 3
    assert not task.done()

    release.set()
    result, cancellation = await asyncio.wait_for(waiter_task, timeout=1)
    assert result == "settled"
    # The level cancellation blocked by the shield must still surface as the
    # deferred-cancellation marker callers re-raise after cleanup.
    assert cancellation is not None


async def test_repeated_edge_cancellation_keeps_callbacks_bounded_and_defers():
    release = asyncio.Event()

    async def cleanup() -> str:
        await release.wait()
        return "settled"

    task = asyncio.create_task(cleanup())
    waiter_task = asyncio.create_task(_await_task_deferring_cancellation(task))
    await asyncio.sleep(0)

    for _ in range(50):
        waiter_task.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    assert _callback_count(task) <= 3
    assert not waiter_task.done()

    release.set()
    result, cancellation = await asyncio.wait_for(waiter_task, timeout=1)
    assert result == "settled"
    assert cancellation is not None


async def test_owned_task_cancellation_still_propagates():
    async def cleanup() -> str:
        await asyncio.Event().wait()
        return "unreachable"

    task = asyncio.create_task(cleanup())
    waiter_task = asyncio.create_task(_await_task_deferring_cancellation(task))
    await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(waiter_task, timeout=1)


async def test_owned_task_exception_propagates():
    async def cleanup() -> str:
        raise RuntimeError("cleanup failed")

    task = asyncio.create_task(cleanup())
    with pytest.raises(RuntimeError, match="cleanup failed"):
        await _await_task_deferring_cancellation(task)


async def test_sse_keepalive_ticks_do_not_grow_pending_chunk_callbacks():
    """Every keepalive timeout used to leave a shield callback on ``pending``."""

    release = asyncio.Event()

    async def quiet_then_one_chunk():
        await release.wait()
        yield "data: chunk\n\n"

    stream = inject_sse_keepalives(
        quiet_then_one_chunk(),
        interval_seconds=0.01,
        keepalive_frame=": keepalive\n\n",
    )

    frames: list[str] = []

    async def consume() -> None:
        async for frame in stream:
            frames.append(frame)
            if frame == "data: chunk\n\n":
                break

    consumer = asyncio.create_task(consume())
    # Let ~20 keepalive intervals elapse against a quiet upstream.
    await asyncio.sleep(0.25)

    pending_tasks = [
        t
        for t in asyncio.all_tasks()
        if t not in {consumer, asyncio.current_task()} and "_next_chunk" in repr(t.get_coro())
    ]
    assert pending_tasks, "keepalive injector should have a pending chunk task"
    assert all(_callback_count(t) <= 3 for t in pending_tasks)

    release.set()
    await asyncio.wait_for(consumer, timeout=1)
    assert ": keepalive\n\n" in frames
    assert frames[-1] == "data: chunk\n\n"


async def test_wait_on_shared_future_fanout():
    """Multiple concurrent waiters receive the shared result with single callback."""
    release = asyncio.Event()

    async def worker() -> int:
        await release.wait()
        return 42

    task = asyncio.create_task(worker())
    waiter1 = asyncio.create_task(wait_on_shared_future(task))
    waiter2 = asyncio.create_task(wait_on_shared_future(task))
    await asyncio.sleep(0)

    # Exactly 1 callback on task, despite 2 waiters
    assert _callback_count(task) == 1
    release.set()

    r1, r2 = await asyncio.gather(waiter1, waiter2)
    assert r1 == 42
    assert r2 == 42
