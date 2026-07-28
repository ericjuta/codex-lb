from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import app.modules.sticky_sessions.cleanup_scheduler as cleanup_scheduler

pytestmark = pytest.mark.unit


def test_build_sticky_session_cleanup_scheduler_respects_enabled_setting(monkeypatch) -> None:
    settings = SimpleNamespace(sticky_session_cleanup_interval_seconds=42, sticky_session_cleanup_enabled=False)
    monkeypatch.setattr(cleanup_scheduler, "get_settings", lambda: settings)

    scheduler = cleanup_scheduler.build_sticky_session_cleanup_scheduler()

    assert scheduler.interval_seconds == 42
    assert scheduler.enabled is False


@pytest.mark.asyncio
async def test_cleanup_once_purges_prompt_cache_only(monkeypatch) -> None:
    """_cleanup_once should purge prompt-cache entries by affinity TTL.
    Durable kinds (STICKY_THREAD, CODEX_SESSION) must NOT be purged."""
    dashboard_settings = SimpleNamespace(openai_cache_affinity_max_age_seconds=600)

    settings_repo = AsyncMock()
    settings_repo.get_or_create = AsyncMock(return_value=dashboard_settings)

    sticky_repo = AsyncMock()
    sticky_repo.purge_prompt_cache_before = AsyncMock(return_value=5)
    sticky_repo.purge_before = AsyncMock(return_value=0)
    bridge_repo = AsyncMock()
    bridge_repo.purge_closed_before = AsyncMock(return_value=2)
    continuity_repo = AsyncMock()
    continuity_repo.purge_before = AsyncMock(return_value=0)

    class FakeSession:
        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, *args):
            pass

    scheduler = cleanup_scheduler.StickySessionCleanupScheduler(
        interval_seconds=60,
        enabled=True,
    )

    with (
        patch.object(cleanup_scheduler, "get_background_session", FakeSession),
        patch.object(cleanup_scheduler, "SettingsRepository", return_value=settings_repo),
        patch.object(cleanup_scheduler, "StickySessionsRepository", return_value=sticky_repo),
        patch.object(cleanup_scheduler, "DurableBridgeRepository", return_value=bridge_repo),
        patch.object(cleanup_scheduler, "WebsocketContinuityStatesRepository", return_value=continuity_repo),
        patch.object(cleanup_scheduler.startup_module, "_bridge_durable_schema_ready", True),
    ):
        await scheduler._cleanup_once()

    sticky_repo.purge_prompt_cache_before.assert_called_once()
    sticky_repo.purge_before.assert_not_called()
    bridge_repo.purge_closed_before.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_once_skips_bridge_purge_when_schema_is_not_ready(monkeypatch) -> None:
    dashboard_settings = SimpleNamespace(openai_cache_affinity_max_age_seconds=600)

    settings_repo = AsyncMock()
    settings_repo.get_or_create = AsyncMock(return_value=dashboard_settings)

    sticky_repo = AsyncMock()
    sticky_repo.purge_prompt_cache_before = AsyncMock(return_value=0)
    bridge_repo = AsyncMock()
    bridge_repo.purge_closed_before = AsyncMock(return_value=0)
    continuity_repo = AsyncMock()
    continuity_repo.purge_before = AsyncMock(return_value=0)

    class FakeSession:
        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, *args):
            pass

    scheduler = cleanup_scheduler.StickySessionCleanupScheduler(
        interval_seconds=60,
        enabled=True,
    )

    with (
        patch.object(cleanup_scheduler, "get_background_session", FakeSession),
        patch.object(cleanup_scheduler, "SettingsRepository", return_value=settings_repo),
        patch.object(cleanup_scheduler, "StickySessionsRepository", return_value=sticky_repo),
        patch.object(cleanup_scheduler, "DurableBridgeRepository", return_value=bridge_repo),
        patch.object(cleanup_scheduler, "WebsocketContinuityStatesRepository", return_value=continuity_repo),
        patch.object(cleanup_scheduler.startup_module, "_bridge_durable_schema_ready", False),
        patch.object(
            cleanup_scheduler,
            "missing_durable_bridge_tables",
            AsyncMock(return_value=("http_bridge_sessions",)),
        ),
    ):
        await scheduler._cleanup_once()

    sticky_repo.purge_prompt_cache_before.assert_called_once()
    bridge_repo.purge_closed_before.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_once_purges_bridge_when_schema_exists_after_startup_flag_reset(monkeypatch) -> None:
    dashboard_settings = SimpleNamespace(openai_cache_affinity_max_age_seconds=600)

    settings_repo = AsyncMock()
    settings_repo.get_or_create = AsyncMock(return_value=dashboard_settings)

    sticky_repo = AsyncMock()
    sticky_repo.purge_prompt_cache_before = AsyncMock(return_value=0)
    bridge_repo = AsyncMock()
    bridge_repo.purge_closed_before = AsyncMock(return_value=1)
    continuity_repo = AsyncMock()
    continuity_repo.purge_before = AsyncMock(return_value=0)

    class FakeSession:
        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, *args):
            pass

    scheduler = cleanup_scheduler.StickySessionCleanupScheduler(
        interval_seconds=60,
        enabled=True,
    )

    with (
        patch.object(cleanup_scheduler, "get_background_session", FakeSession),
        patch.object(cleanup_scheduler, "SettingsRepository", return_value=settings_repo),
        patch.object(cleanup_scheduler, "StickySessionsRepository", return_value=sticky_repo),
        patch.object(cleanup_scheduler, "DurableBridgeRepository", return_value=bridge_repo),
        patch.object(cleanup_scheduler, "WebsocketContinuityStatesRepository", return_value=continuity_repo),
        patch.object(cleanup_scheduler.startup_module, "_bridge_durable_schema_ready", False),
        patch.object(cleanup_scheduler, "missing_durable_bridge_tables", AsyncMock(return_value=())),
    ):
        await scheduler._cleanup_once()

    sticky_repo.purge_prompt_cache_before.assert_called_once()
    bridge_repo.purge_closed_before.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_once_purges_stale_websocket_continuity_states() -> None:
    dashboard_settings = SimpleNamespace(openai_cache_affinity_max_age_seconds=600)

    settings_repo = AsyncMock()
    settings_repo.get_or_create = AsyncMock(return_value=dashboard_settings)

    sticky_repo = AsyncMock()
    sticky_repo.purge_prompt_cache_before = AsyncMock(return_value=0)
    bridge_repo = AsyncMock()
    bridge_repo.purge_closed_before = AsyncMock(return_value=0)
    continuity_repo = AsyncMock()
    continuity_repo.purge_before = AsyncMock(return_value=3)

    class FakeSession:
        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, *args):
            pass

    scheduler = cleanup_scheduler.StickySessionCleanupScheduler(
        interval_seconds=60,
        enabled=True,
    )

    before = cleanup_scheduler.utcnow()
    with (
        patch.object(cleanup_scheduler, "get_background_session", FakeSession),
        patch.object(cleanup_scheduler, "SettingsRepository", return_value=settings_repo),
        patch.object(cleanup_scheduler, "StickySessionsRepository", return_value=sticky_repo),
        patch.object(cleanup_scheduler, "DurableBridgeRepository", return_value=bridge_repo),
        patch.object(cleanup_scheduler, "WebsocketContinuityStatesRepository", return_value=continuity_repo),
        patch.object(cleanup_scheduler.startup_module, "_bridge_durable_schema_ready", True),
    ):
        await scheduler._cleanup_once()
    after = cleanup_scheduler.utcnow()

    continuity_repo.purge_before.assert_called_once()
    (cutoff,) = continuity_repo.purge_before.call_args.args
    max_age = timedelta(hours=cleanup_scheduler._WEBSOCKET_CONTINUITY_STATE_MAX_AGE_HOURS)
    assert before - max_age <= cutoff <= after - max_age


@pytest.mark.asyncio
async def test_cleanup_once_survives_missing_websocket_continuity_table() -> None:
    dashboard_settings = SimpleNamespace(openai_cache_affinity_max_age_seconds=600)

    settings_repo = AsyncMock()
    settings_repo.get_or_create = AsyncMock(return_value=dashboard_settings)

    sticky_repo = AsyncMock()
    sticky_repo.purge_prompt_cache_before = AsyncMock(return_value=1)
    bridge_repo = AsyncMock()
    bridge_repo.purge_closed_before = AsyncMock(return_value=1)
    continuity_repo = AsyncMock()
    continuity_repo.purge_before = AsyncMock(side_effect=RuntimeError("no such table: websocket_continuity_states"))

    class FakeSession:
        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, *args):
            pass

    scheduler = cleanup_scheduler.StickySessionCleanupScheduler(
        interval_seconds=60,
        enabled=True,
    )

    with (
        patch.object(cleanup_scheduler, "get_background_session", FakeSession),
        patch.object(cleanup_scheduler, "SettingsRepository", return_value=settings_repo),
        patch.object(cleanup_scheduler, "StickySessionsRepository", return_value=sticky_repo),
        patch.object(cleanup_scheduler, "DurableBridgeRepository", return_value=bridge_repo),
        patch.object(cleanup_scheduler, "WebsocketContinuityStatesRepository", return_value=continuity_repo),
        patch.object(cleanup_scheduler.startup_module, "_bridge_durable_schema_ready", True),
    ):
        await scheduler._cleanup_once()

    sticky_repo.purge_prompt_cache_before.assert_called_once()
    bridge_repo.purge_closed_before.assert_called_once()
    continuity_repo.purge_before.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_once_purges_aged_codex_sessions(monkeypatch) -> None:
    """codex_session rows older than the retention window are purged; the
    cutoff must reflect the configured retention days."""
    dashboard_settings = SimpleNamespace(openai_cache_affinity_max_age_seconds=600)

    settings_repo = AsyncMock()
    settings_repo.get_or_create = AsyncMock(return_value=dashboard_settings)

    sticky_repo = AsyncMock()
    sticky_repo.purge_prompt_cache_before = AsyncMock(return_value=0)
    sticky_repo.purge_codex_session_before = AsyncMock(return_value=7)
    sticky_repo.purge_before = AsyncMock(return_value=0)
    bridge_repo = AsyncMock()
    bridge_repo.purge_closed_before = AsyncMock(return_value=0)
    continuity_repo = AsyncMock()
    continuity_repo.purge_before = AsyncMock(return_value=0)

    runtime_settings = SimpleNamespace(sticky_codex_session_retention_days=30)
    monkeypatch.setattr(cleanup_scheduler, "get_settings", lambda: runtime_settings)

    class FakeSession:
        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, *args):
            pass

    scheduler = cleanup_scheduler.StickySessionCleanupScheduler(
        interval_seconds=60,
        enabled=True,
    )

    before = cleanup_scheduler.utcnow()
    with (
        patch.object(cleanup_scheduler, "get_background_session", FakeSession),
        patch.object(cleanup_scheduler, "SettingsRepository", return_value=settings_repo),
        patch.object(cleanup_scheduler, "StickySessionsRepository", return_value=sticky_repo),
        patch.object(cleanup_scheduler, "DurableBridgeRepository", return_value=bridge_repo),
        patch.object(cleanup_scheduler, "WebsocketContinuityStatesRepository", return_value=continuity_repo),
        patch.object(cleanup_scheduler.startup_module, "_bridge_durable_schema_ready", True),
    ):
        await scheduler._cleanup_once()
    after = cleanup_scheduler.utcnow()

    sticky_repo.purge_codex_session_before.assert_called_once()
    (cutoff,) = sticky_repo.purge_codex_session_before.call_args.args
    assert before - timedelta(days=30) <= cutoff <= after - timedelta(days=30)
    # sticky_thread must never be purged: only the kind-scoped helpers run.
    sticky_repo.purge_before.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_once_zero_retention_disables_codex_session_purge(monkeypatch) -> None:
    dashboard_settings = SimpleNamespace(openai_cache_affinity_max_age_seconds=600)

    settings_repo = AsyncMock()
    settings_repo.get_or_create = AsyncMock(return_value=dashboard_settings)

    sticky_repo = AsyncMock()
    sticky_repo.purge_prompt_cache_before = AsyncMock(return_value=0)
    sticky_repo.purge_codex_session_before = AsyncMock(return_value=0)
    bridge_repo = AsyncMock()
    bridge_repo.purge_closed_before = AsyncMock(return_value=0)
    continuity_repo = AsyncMock()
    continuity_repo.purge_before = AsyncMock(return_value=0)

    runtime_settings = SimpleNamespace(sticky_codex_session_retention_days=0)
    monkeypatch.setattr(cleanup_scheduler, "get_settings", lambda: runtime_settings)

    class FakeSession:
        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, *args):
            pass

    scheduler = cleanup_scheduler.StickySessionCleanupScheduler(
        interval_seconds=60,
        enabled=True,
    )

    with (
        patch.object(cleanup_scheduler, "get_background_session", FakeSession),
        patch.object(cleanup_scheduler, "SettingsRepository", return_value=settings_repo),
        patch.object(cleanup_scheduler, "StickySessionsRepository", return_value=sticky_repo),
        patch.object(cleanup_scheduler, "DurableBridgeRepository", return_value=bridge_repo),
        patch.object(cleanup_scheduler, "WebsocketContinuityStatesRepository", return_value=continuity_repo),
        patch.object(cleanup_scheduler.startup_module, "_bridge_durable_schema_ready", True),
    ):
        await scheduler._cleanup_once()

    sticky_repo.purge_codex_session_before.assert_not_called()
    sticky_repo.purge_prompt_cache_before.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_once_survives_codex_session_purge_failure(monkeypatch) -> None:
    """A codex-session purge failure must not break the other cleanup steps."""
    dashboard_settings = SimpleNamespace(openai_cache_affinity_max_age_seconds=600)

    settings_repo = AsyncMock()
    settings_repo.get_or_create = AsyncMock(return_value=dashboard_settings)

    sticky_repo = AsyncMock()
    sticky_repo.purge_prompt_cache_before = AsyncMock(return_value=0)
    sticky_repo.purge_codex_session_before = AsyncMock(side_effect=RuntimeError("boom"))
    bridge_repo = AsyncMock()
    bridge_repo.purge_closed_before = AsyncMock(return_value=0)
    continuity_repo = AsyncMock()
    continuity_repo.purge_before = AsyncMock(return_value=0)

    runtime_settings = SimpleNamespace(sticky_codex_session_retention_days=30)
    monkeypatch.setattr(cleanup_scheduler, "get_settings", lambda: runtime_settings)

    class FakeSession:
        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, *args):
            pass

    scheduler = cleanup_scheduler.StickySessionCleanupScheduler(
        interval_seconds=60,
        enabled=True,
    )

    with (
        patch.object(cleanup_scheduler, "get_background_session", FakeSession),
        patch.object(cleanup_scheduler, "SettingsRepository", return_value=settings_repo),
        patch.object(cleanup_scheduler, "StickySessionsRepository", return_value=sticky_repo),
        patch.object(cleanup_scheduler, "DurableBridgeRepository", return_value=bridge_repo),
        patch.object(cleanup_scheduler, "WebsocketContinuityStatesRepository", return_value=continuity_repo),
        patch.object(cleanup_scheduler.startup_module, "_bridge_durable_schema_ready", True),
    ):
        await scheduler._cleanup_once()

    bridge_repo.purge_closed_before.assert_called_once()
    continuity_repo.purge_before.assert_called_once()
