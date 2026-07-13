from __future__ import annotations

import asyncio
import contextlib
import importlib
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol, cast

from sqlalchemy import func, select

from app.core.config.settings import get_settings
from app.core.metrics.prometheus import PROMETHEUS_AVAILABLE, prompt_cache_ratio
from app.core.utils.time import utcnow
from app.db.models import RequestLog
from app.db.session import get_background_session

logger = logging.getLogger(__name__)


class _LeaderElectionLike(Protocol):
    async def try_acquire(self) -> bool: ...


def _get_leader_election() -> _LeaderElectionLike:
    module = importlib.import_module("app.core.scheduling.leader_election")
    return cast(_LeaderElectionLike, module.get_leader_election())


@dataclass(slots=True)
class PromptCacheCanaryScheduler:
    """Samples per-model prompt-cache hit ratio and warns on collapse."""

    interval_seconds: int
    window_seconds: int
    min_input_tokens: int
    ratio_threshold: float
    enabled: bool
    _task: asyncio.Task[None] | None = None
    _stop: asyncio.Event = field(default_factory=asyncio.Event)

    async def start(self) -> None:
        if not self.enabled:
            return
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._sample_once()
            except Exception:
                logger.exception("Prompt-cache canary sample failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue

    async def _sample_once(self) -> None:
        if not await _get_leader_election().try_acquire():
            return
        cutoff = utcnow() - timedelta(seconds=self.window_seconds)
        async with get_background_session() as session:
            rows = (
                await session.execute(
                    select(
                        RequestLog.model,
                        func.coalesce(func.sum(RequestLog.input_tokens), 0).label("input_tokens"),
                        func.coalesce(func.sum(RequestLog.cached_input_tokens), 0).label("cached_input_tokens"),
                    )
                    .where(
                        RequestLog.requested_at >= cutoff,
                        RequestLog.request_kind == "normal",
                        RequestLog.status == "success",
                        RequestLog.deleted_at.is_(None),
                    )
                    .group_by(RequestLog.model)
                )
            ).all()
        for model, input_tokens, cached_input_tokens in rows:
            if not model or input_tokens <= 0:
                continue
            ratio = cached_input_tokens / input_tokens
            if PROMETHEUS_AVAILABLE and prompt_cache_ratio is not None:
                prompt_cache_ratio.labels(model=model).set(ratio)
            if input_tokens >= self.min_input_tokens and ratio < self.ratio_threshold:
                logger.warning(
                    "Prompt-cache ratio collapsed model=%s ratio=%.3f input_tokens=%s threshold=%.2f window_seconds=%s",
                    model,
                    ratio,
                    input_tokens,
                    self.ratio_threshold,
                    self.window_seconds,
                )


def build_prompt_cache_canary_scheduler() -> PromptCacheCanaryScheduler:
    settings = get_settings()
    return PromptCacheCanaryScheduler(
        interval_seconds=settings.prompt_cache_canary_interval_seconds,
        window_seconds=settings.prompt_cache_canary_window_seconds,
        min_input_tokens=settings.prompt_cache_canary_min_input_tokens,
        ratio_threshold=settings.prompt_cache_canary_ratio_threshold,
        enabled=settings.prompt_cache_canary_enabled,
    )
