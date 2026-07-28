from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.modules.request_logs.prompt_cache_canary as canary_module

pytestmark = pytest.mark.unit


def _make_scheduler(**overrides) -> canary_module.PromptCacheCanaryScheduler:
    kwargs: dict[str, Any] = {
        "interval_seconds": 300,
        "window_seconds": 3600,
        "min_input_tokens": 1_000_000,
        "ratio_threshold": 0.5,
        "model_ratio_thresholds": {},
        "uncached_tokens_threshold": 0,
        "model_uncached_tokens_thresholds": {},
        "enabled": True,
    }
    kwargs.update(overrides)
    return canary_module.PromptCacheCanaryScheduler(**kwargs)


def _fake_session_returning(rows: list[tuple[str | None, int, int, int]]):
    result = MagicMock()
    result.all.return_value = rows
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)

    class FakeSessionCtx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            pass

    return FakeSessionCtx


class _FakeGaugeChild:
    def __init__(self) -> None:
        self.value: float | None = None

    def set(self, value: float) -> None:
        self.value = value


class _FakeGauge:
    def __init__(self) -> None:
        self.samples: dict[str, _FakeGaugeChild] = {}

    def labels(self, model: str) -> _FakeGaugeChild:
        return self.samples.setdefault(model, _FakeGaugeChild())


def test_build_respects_settings(monkeypatch) -> None:
    settings = SimpleNamespace(
        prompt_cache_canary_interval_seconds=60,
        prompt_cache_canary_window_seconds=1200,
        prompt_cache_canary_min_input_tokens=500,
        prompt_cache_canary_ratio_threshold=0.25,
        prompt_cache_canary_model_ratio_thresholds={"gpt-x": 0.1},
        prompt_cache_canary_uncached_tokens_threshold=25_000,
        prompt_cache_canary_model_uncached_tokens_thresholds={"gpt-x": 10_000},
        prompt_cache_canary_enabled=False,
    )
    monkeypatch.setattr(canary_module, "get_settings", lambda: settings)
    scheduler = canary_module.build_prompt_cache_canary_scheduler()
    assert scheduler.interval_seconds == 60
    assert scheduler.window_seconds == 1200
    assert scheduler.min_input_tokens == 500
    assert scheduler.ratio_threshold == 0.25
    assert scheduler.model_ratio_thresholds == {"gpt-x": 0.1}
    assert scheduler.uncached_tokens_threshold == 25_000
    assert scheduler.model_uncached_tokens_thresholds == {"gpt-x": 10_000}
    assert scheduler.enabled is False


@pytest.mark.asyncio
async def test_disabled_scheduler_does_not_start() -> None:
    scheduler = _make_scheduler(enabled=False)
    await scheduler.start()
    assert scheduler._task is None


@pytest.mark.asyncio
async def test_healthy_model_updates_gauge_without_warning(caplog) -> None:
    gauge = _FakeGauge()
    leader = AsyncMock()
    leader.try_acquire = AsyncMock(return_value=True)
    scheduler = _make_scheduler()
    with (
        patch.object(
            canary_module,
            "get_background_session",
            _fake_session_returning([("gpt-5.6-luna", 2_000_000, 1_900_000, 20)]),
        ),
        patch.object(canary_module, "PROMETHEUS_AVAILABLE", True),
        patch.object(canary_module, "prompt_cache_ratio", gauge),
        patch.object(canary_module, "_get_leader_election", lambda: leader),
        caplog.at_level(logging.WARNING, logger=canary_module.logger.name),
    ):
        await scheduler._sample_once()
    assert gauge.samples["gpt-5.6-luna"].value == pytest.approx(0.95)
    assert not caplog.records


@pytest.mark.asyncio
async def test_collapsed_ratio_emits_warning(caplog) -> None:
    gauge = _FakeGauge()
    leader = AsyncMock()
    leader.try_acquire = AsyncMock(return_value=True)
    scheduler = _make_scheduler()
    with (
        patch.object(
            canary_module, "get_background_session", _fake_session_returning([("gpt-5.6-luna", 2_000_000, 40_000, 20)])
        ),
        patch.object(canary_module, "PROMETHEUS_AVAILABLE", True),
        patch.object(canary_module, "prompt_cache_ratio", gauge),
        patch.object(canary_module, "_get_leader_election", lambda: leader),
        caplog.at_level(logging.WARNING, logger=canary_module.logger.name),
    ):
        await scheduler._sample_once()
    assert gauge.samples["gpt-5.6-luna"].value == pytest.approx(0.02)
    assert len(caplog.records) == 1
    assert "gpt-5.6-luna" in caplog.records[0].getMessage()


@pytest.mark.asyncio
async def test_low_volume_model_does_not_warn(caplog) -> None:
    gauge = _FakeGauge()
    leader = AsyncMock()
    leader.try_acquire = AsyncMock(return_value=True)
    scheduler = _make_scheduler()
    with (
        patch.object(canary_module, "get_background_session", _fake_session_returning([("gpt-5.4", 10_000, 0, 5)])),
        patch.object(canary_module, "PROMETHEUS_AVAILABLE", True),
        patch.object(canary_module, "prompt_cache_ratio", gauge),
        patch.object(canary_module, "_get_leader_election", lambda: leader),
        caplog.at_level(logging.WARNING, logger=canary_module.logger.name),
    ):
        await scheduler._sample_once()
    assert gauge.samples["gpt-5.4"].value == 0.0
    assert not caplog.records


@pytest.mark.asyncio
async def test_non_leader_skips_sampling() -> None:
    leader = AsyncMock()
    leader.try_acquire = AsyncMock(return_value=False)
    session_factory = MagicMock()
    scheduler = _make_scheduler()
    with (
        patch.object(canary_module, "get_background_session", session_factory),
        patch.object(canary_module, "_get_leader_election", lambda: leader),
    ):
        await scheduler._sample_once()
    session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_null_model_and_zero_input_are_skipped(caplog) -> None:
    gauge = _FakeGauge()
    leader = AsyncMock()
    leader.try_acquire = AsyncMock(return_value=True)
    scheduler = _make_scheduler()
    with (
        patch.object(
            canary_module, "get_background_session", _fake_session_returning([(None, 100, 0, 1), ("gpt-x", 0, 0, 1)])
        ),
        patch.object(canary_module, "PROMETHEUS_AVAILABLE", True),
        patch.object(canary_module, "prompt_cache_ratio", gauge),
        patch.object(canary_module, "_get_leader_election", lambda: leader),
        caplog.at_level(logging.WARNING, logger=canary_module.logger.name),
    ):
        await scheduler._sample_once()
    assert gauge.samples == {}
    assert not caplog.records


def _patched_sample(scheduler, rows, ratio_gauge, uncached_gauge, caplog):
    leader = AsyncMock()
    leader.try_acquire = AsyncMock(return_value=True)
    return (
        patch.object(canary_module, "get_background_session", _fake_session_returning(rows)),
        patch.object(canary_module, "PROMETHEUS_AVAILABLE", True),
        patch.object(canary_module, "prompt_cache_ratio", ratio_gauge),
        patch.object(canary_module, "prompt_cache_uncached_tokens_per_request", uncached_gauge),
        patch.object(canary_module, "_get_leader_election", lambda: leader),
        caplog.at_level(logging.WARNING, logger=canary_module.logger.name),
    )


@pytest.mark.asyncio
async def test_uncached_tokens_gauge_exported(caplog) -> None:
    ratio_gauge, uncached_gauge = _FakeGauge(), _FakeGauge()
    scheduler = _make_scheduler()
    ctxs = _patched_sample(scheduler, [("gpt-5.6-sol", 2_000_000, 1_800_000, 40)], ratio_gauge, uncached_gauge, caplog)
    with ctxs[0], ctxs[1], ctxs[2], ctxs[3], ctxs[4], ctxs[5]:
        await scheduler._sample_once()
    assert uncached_gauge.samples["gpt-5.6-sol"].value == pytest.approx(5_000)


@pytest.mark.asyncio
async def test_delta_shaped_traffic_does_not_fire_uncached_alert(caplog) -> None:
    # Low ratio (0.3) but low absolute uncached tokens; no uncached threshold set.
    ratio_gauge, uncached_gauge = _FakeGauge(), _FakeGauge()
    scheduler = _make_scheduler(model_ratio_thresholds={"gpt-5.3-codex-spark": 0.15})
    ctxs = _patched_sample(
        scheduler, [("gpt-5.3-codex-spark", 2_000_000, 600_000, 500)], ratio_gauge, uncached_gauge, caplog
    )
    with ctxs[0], ctxs[1], ctxs[2], ctxs[3], ctxs[4], ctxs[5]:
        await scheduler._sample_once()
    assert not caplog.records


@pytest.mark.asyncio
async def test_per_model_ratio_override_beats_blanket(caplog) -> None:
    # Ratio 0.3 is below blanket 0.5 but above the per-model 0.15 override: no warning.
    ratio_gauge, uncached_gauge = _FakeGauge(), _FakeGauge()
    scheduler = _make_scheduler(model_ratio_thresholds={"gpt-5.3-codex-spark": 0.15})
    ctxs = _patched_sample(
        scheduler,
        [("gpt-5.3-codex-spark", 2_000_000, 600_000, 500), ("gpt-5.6-sol", 2_000_000, 600_000, 20)],
        ratio_gauge,
        uncached_gauge,
        caplog,
    )
    with ctxs[0], ctxs[1], ctxs[2], ctxs[3], ctxs[4], ctxs[5]:
        await scheduler._sample_once()
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1
    assert "gpt-5.6-sol" in messages[0]


@pytest.mark.asyncio
async def test_uncached_regression_alerts_despite_healthy_ratio(caplog) -> None:
    # Ratio 0.9 is healthy, but 100k uncached tokens/request exceeds the model threshold.
    ratio_gauge, uncached_gauge = _FakeGauge(), _FakeGauge()
    scheduler = _make_scheduler(model_uncached_tokens_thresholds={"gpt-5.6-sol": 50_000})
    ctxs = _patched_sample(scheduler, [("gpt-5.6-sol", 10_000_000, 9_000_000, 10)], ratio_gauge, uncached_gauge, caplog)
    with ctxs[0], ctxs[1], ctxs[2], ctxs[3], ctxs[4], ctxs[5]:
        await scheduler._sample_once()
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1
    assert "uncached tokens regressed" in messages[0]
    assert "gpt-5.6-sol" in messages[0]


@pytest.mark.asyncio
async def test_zero_uncached_threshold_disables_alerting(caplog) -> None:
    ratio_gauge, uncached_gauge = _FakeGauge(), _FakeGauge()
    scheduler = _make_scheduler(uncached_tokens_threshold=0)
    ctxs = _patched_sample(scheduler, [("gpt-5.6-sol", 10_000_000, 9_000_000, 10)], ratio_gauge, uncached_gauge, caplog)
    with ctxs[0], ctxs[1], ctxs[2], ctxs[3], ctxs[4], ctxs[5]:
        await scheduler._sample_once()
    assert not caplog.records
