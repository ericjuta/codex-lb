from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.modules.accounts.usage_rollup_scheduler as rollup_scheduler
from app.modules.accounts.usage_rollup_scheduler import AccountUsageRollupScheduler

pytestmark = pytest.mark.unit


def test_build_account_usage_rollup_scheduler_uses_constant_interval() -> None:
    scheduler = rollup_scheduler.build_account_usage_rollup_scheduler()
    assert scheduler.interval_seconds == rollup_scheduler.FOLD_INTERVAL_SECONDS


@pytest.mark.asyncio
async def test_fold_once_skips_when_not_leader(monkeypatch) -> None:
    leader = SimpleNamespace(try_acquire=AsyncMock(return_value=False))
    monkeypatch.setattr(rollup_scheduler, "_get_leader_election", lambda: leader)
    fold = AsyncMock()
    hourly = AsyncMock()
    monkeypatch.setattr(rollup_scheduler, "run_fold_pass", fold)
    monkeypatch.setattr(rollup_scheduler, "run_hourly_fold_pass", hourly)

    await AccountUsageRollupScheduler(interval_seconds=1)._fold_once()

    fold.assert_not_called()
    hourly.assert_not_called()
    leader.try_acquire.assert_awaited_once()


@pytest.mark.asyncio
async def test_fold_once_runs_both_passes_as_leader(monkeypatch) -> None:
    leader = SimpleNamespace(try_acquire=AsyncMock(return_value=True))
    monkeypatch.setattr(rollup_scheduler, "_get_leader_election", lambda: leader)
    fold = AsyncMock(return_value=2)
    hourly = AsyncMock(return_value=1)
    monkeypatch.setattr(rollup_scheduler, "run_fold_pass", fold)
    monkeypatch.setattr(rollup_scheduler, "run_hourly_fold_pass", hourly)

    await AccountUsageRollupScheduler(interval_seconds=1)._fold_once()

    fold.assert_awaited_once()
    hourly.assert_awaited_once()
    leader.try_acquire.assert_awaited_once()


@pytest.mark.asyncio
async def test_fold_once_swallows_fold_errors(monkeypatch) -> None:
    leader = SimpleNamespace(try_acquire=AsyncMock(return_value=True))
    monkeypatch.setattr(rollup_scheduler, "_get_leader_election", lambda: leader)
    fold = AsyncMock(side_effect=RuntimeError("db down"))
    hourly = AsyncMock(side_effect=RuntimeError("db down"))
    monkeypatch.setattr(rollup_scheduler, "run_fold_pass", fold)
    monkeypatch.setattr(rollup_scheduler, "run_hourly_fold_pass", hourly)

    await AccountUsageRollupScheduler(interval_seconds=1)._fold_once()

    fold.assert_awaited_once()
    hourly.assert_awaited_once()


@pytest.mark.asyncio
async def test_fold_once_runs_hourly_pass_even_when_lifetime_pass_fails(monkeypatch) -> None:
    """Blast-radius isolation: a lifetime-fold failure must not stop the
    hourly time-axis fold (and vice versa) — each has its own watermark and
    retention only pauses via the min-gate."""
    leader = SimpleNamespace(try_acquire=AsyncMock(return_value=True))
    monkeypatch.setattr(rollup_scheduler, "_get_leader_election", lambda: leader)
    fold = AsyncMock(side_effect=RuntimeError("lifetime fold broken"))
    hourly = AsyncMock(return_value=3)
    monkeypatch.setattr(rollup_scheduler, "run_fold_pass", fold)
    monkeypatch.setattr(rollup_scheduler, "run_hourly_fold_pass", hourly)

    await AccountUsageRollupScheduler(interval_seconds=1)._fold_once()

    fold.assert_awaited_once()
    hourly.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_folds_immediately_and_stop_cancels(monkeypatch) -> None:
    leader = SimpleNamespace(try_acquire=AsyncMock(return_value=True))
    monkeypatch.setattr(rollup_scheduler, "_get_leader_election", lambda: leader)
    folded = asyncio.Event()

    async def _fold(**_kwargs):
        folded.set()
        return 0

    monkeypatch.setattr(rollup_scheduler, "run_fold_pass", _fold)
    monkeypatch.setattr(rollup_scheduler, "run_hourly_fold_pass", AsyncMock(return_value=0))

    scheduler = AccountUsageRollupScheduler(interval_seconds=3600)
    await scheduler.start()
    await asyncio.wait_for(folded.wait(), timeout=5)
    await scheduler.stop()
    assert scheduler._task is None
