from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest

import app.modules.oauth.service as oauth_module
from app.core.clients.oauth import DeviceCode, OAuthError, OAuthTokens
from app.core.crypto import TokenEncryptor
from app.core.utils.time import utcnow
from app.db.models import OAuthFlowState
from app.db.session import SessionLocal
from app.modules.accounts.repository import AccountsRepository
from app.modules.oauth.repository import OAuthFlowRecord, OAuthFlowRepository
from app.modules.oauth.schemas import OauthCompleteRequest, OauthStartRequest

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _oauth_replica_schema(db_setup):
    del db_setup


def _service(store: oauth_module.OAuthStateStore) -> oauth_module.OauthService:
    @asynccontextmanager
    async def repo_factory():
        async with SessionLocal() as session:
            yield AccountsRepository(session)

    accounts = cast(
        AccountsRepository,
        SimpleNamespace(list_accounts=AsyncMock(return_value=[])),
    )
    return oauth_module.OauthService(accounts, repo_factory=repo_factory, store=store)


def _state_token(authorization_url: str) -> str:
    return parse_qs(urlparse(authorization_url).query)["state"][0]


@pytest.mark.asyncio
async def test_repository_encrypts_expires_and_enforces_monotonic_status_and_slot():
    encryptor = TokenEncryptor()
    async with SessionLocal() as session:
        repo = OAuthFlowRepository(session, encryptor)
        await repo.create(
            OAuthFlowRecord(
                flow_id="flow-live",
                method="browser",
                status="pending",
                state_token="state-live",
                code_verifier="secret-verifier",
                expires_at=utcnow() + timedelta(minutes=5),
            )
        )
        raw = await session.get(OAuthFlowState, "flow-live")
        assert raw is not None
        assert raw.code_verifier_encrypted != b"secret-verifier"
        assert (await repo.get_by_flow_id("flow-live")).code_verifier == "secret-verifier"  # type: ignore[union-attr]

        assert await repo.set_status("flow-live", status="success", error_message=None)
        assert not await repo.set_status(
            "flow-live",
            status="error",
            error_message="late loser",
        )
        assert (await repo.get_by_flow_id("flow-live")).status == "success"  # type: ignore[union-attr]

        await repo.create(
            OAuthFlowRecord(
                flow_id="flow-expired",
                method="browser",
                status="pending",
                expires_at=utcnow() - timedelta(seconds=1),
            )
        )
        assert await repo.get_by_flow_id("flow-expired") is None

        await repo.claim_device_slot("device-old")
        await repo.claim_device_slot("device-current")
        assert await repo.current_device_slot_flow_id() == "device-current"
        assert not await repo.consume_device_slot("device-old")
        assert await repo.consume_device_slot("device-current")


@pytest.mark.asyncio
async def test_browser_callback_and_duplicate_reconcile_across_replicas(monkeypatch):
    async def no_callback_server(self) -> None:
        del self

    async def no_route():
        return None

    tokens = OAuthTokens(
        access_token="access",
        refresh_token="refresh",
        id_token="header.eyJlbWFpbCI6InJlcGxpY2FAZXhhbXBsZS5jb20ifQ.sig",
    )
    exchange = AsyncMock(return_value=tokens)
    monkeypatch.setattr(oauth_module.OAuthCallbackServer, "start", no_callback_server)
    monkeypatch.setattr(oauth_module, "_oauth_route", no_route)
    monkeypatch.setattr(oauth_module, "exchange_authorization_code", exchange)

    replica_a = _service(oauth_module.OAuthStateStore())
    replica_b = _service(oauth_module.OAuthStateStore())
    persist_tokens = AsyncMock()
    monkeypatch.setattr(replica_b, "_persist_tokens", persist_tokens)

    started = await replica_a.start_oauth(OauthStartRequest(force_method="browser"))
    assert started.flow_id is not None
    assert started.authorization_url is not None
    state = _state_token(started.authorization_url)

    completed = await replica_b.manual_callback(
        f"http://localhost:1455/auth/callback?code=one&state={state}",
        flow_id=started.flow_id,
    )
    assert completed.status == "success"
    persist_tokens.assert_awaited_once_with(tokens)
    assert (await replica_a.oauth_status(started.flow_id)).status == "success"

    exchange.reset_mock(side_effect=True)
    exchange.side_effect = AssertionError("duplicate callback replayed the code")
    duplicate = await replica_a.manual_callback(
        f"http://localhost:1455/auth/callback?code=one&state={state}",
        flow_id=started.flow_id,
    )
    assert duplicate.status == "success"
    exchange.assert_not_awaited()


@pytest.mark.asyncio
async def test_callback_loser_reports_durable_success(monkeypatch):
    async def no_callback_server(self) -> None:
        del self

    async def no_route():
        return None

    monkeypatch.setattr(oauth_module.OAuthCallbackServer, "start", no_callback_server)
    monkeypatch.setattr(oauth_module, "_oauth_route", no_route)
    replica = _service(oauth_module.OAuthStateStore())
    started = await replica.start_oauth(OauthStartRequest(force_method="browser"))
    assert started.flow_id is not None
    assert started.authorization_url is not None
    state = _state_token(started.authorization_url)

    async def racing_exchange(**_kwargs):
        async with SessionLocal() as session:
            applied = await OAuthFlowRepository(session, TokenEncryptor()).set_status(
                started.flow_id,
                status="success",
                error_message=None,
            )
            assert applied
        raise OAuthError("invalid_grant", "Authorization code was already consumed")

    monkeypatch.setattr(oauth_module, "exchange_authorization_code", racing_exchange)
    result = await replica.manual_callback(
        f"http://localhost:1455/auth/callback?code=race&state={state}",
        flow_id=started.flow_id,
    )
    assert result.status == "success"
    async with replica._store.lock:
        local = replica._store.get_flow_locked(started.flow_id)
        assert local is not None
        assert local.status == "success"


@pytest.mark.asyncio
async def test_expired_durable_flow_invalidates_origin_replica(monkeypatch):
    async def no_callback_server(self) -> None:
        del self

    monkeypatch.setattr(oauth_module.OAuthCallbackServer, "start", no_callback_server)
    replica = _service(oauth_module.OAuthStateStore())
    started = await replica.start_oauth(OauthStartRequest(force_method="browser"))
    assert started.flow_id is not None
    assert started.authorization_url is not None
    state = _state_token(started.authorization_url)

    async with SessionLocal() as session:
        row = await session.get(OAuthFlowState, started.flow_id)
        assert row is not None
        row.expires_at = utcnow() - timedelta(seconds=1)
        await session.commit()

    exchange = AsyncMock()
    monkeypatch.setattr(oauth_module, "exchange_authorization_code", exchange)
    result = await replica.manual_callback(
        f"http://localhost:1455/auth/callback?code=expired&state={state}",
        flow_id=started.flow_id,
    )
    assert result.status == "error"
    exchange.assert_not_awaited()
    async with replica._store.lock:
        assert replica._store.get_flow_locked(started.flow_id) is None


@pytest.mark.asyncio
async def test_concurrent_device_starts_leave_one_database_owner(monkeypatch):
    counter = 0

    async def fake_device_code(**_kwargs):
        nonlocal counter
        counter += 1
        suffix = str(counter)
        return DeviceCode(
            verification_url="https://example.invalid/device",
            user_code=f"code-{suffix}",
            device_auth_id=f"auth-{suffix}",
            interval_seconds=60,
            expires_in_seconds=300,
        )

    monkeypatch.setattr(oauth_module, "request_device_code", fake_device_code)
    monkeypatch.setattr(oauth_module, "_oauth_route", AsyncMock(return_value=None))
    monkeypatch.setattr(
        oauth_module.OauthService,
        "_ensure_device_poll_task_locked",
        lambda _self, _state: True,
    )

    replica_a = _service(oauth_module.OAuthStateStore())
    replica_b = _service(oauth_module.OAuthStateStore())
    start_a, start_b = await asyncio.gather(
        replica_a.start_oauth(OauthStartRequest(force_method="device")),
        replica_b.start_oauth(OauthStartRequest(force_method="device")),
    )

    async with SessionLocal() as session:
        repo = OAuthFlowRepository(session, TokenEncryptor())
        current = await repo.current_device_slot_flow_id()
        assert current in {start_a.flow_id, start_b.flow_id}
        other = start_b.flow_id if current == start_a.flow_id else start_a.flow_id
        assert other is not None
        assert not await repo.consume_device_slot(other)
        assert current is not None
        assert await repo.consume_device_slot(current)


@pytest.mark.asyncio
async def test_superseded_device_poller_writes_nothing(monkeypatch):
    replica = _service(oauth_module.OAuthStateStore())
    flow = oauth_module.OAuthState(
        flow_id="superseded",
        method="device",
        status="pending",
        device_auth_id="auth",
        user_code="code",
        interval_seconds=0,
        expires_at=oauth_module.time.time() + 60,
    )
    async with replica._store.lock:
        replica._store.remember_flow_locked(flow)

    async with SessionLocal() as session:
        repo = OAuthFlowRepository(session, TokenEncryptor())
        await repo.create(
            OAuthFlowRecord(
                flow_id="superseded",
                method="device",
                status="pending",
                device_auth_id="auth",
                user_code="code",
                expires_at=utcnow() + timedelta(minutes=1),
            )
        )
        await repo.claim_device_slot("replacement")

    monkeypatch.setattr(oauth_module, "_oauth_route", AsyncMock(return_value=None))
    monkeypatch.setattr(
        oauth_module,
        "exchange_device_token",
        AsyncMock(return_value=OAuthTokens("access", "refresh", "id")),
    )
    persist_tokens = AsyncMock()
    monkeypatch.setattr(replica, "_persist_tokens", persist_tokens)

    await replica._poll_device_tokens(
        "superseded",
        oauth_module.DevicePollContext(
            device_auth_id="auth",
            user_code="code",
            interval_seconds=0,
            expires_at=oauth_module.time.time() + 60,
        ),
    )
    persist_tokens.assert_not_awaited()
    async with SessionLocal() as session:
        repo = OAuthFlowRepository(session, TokenEncryptor())
        assert (await repo.get_by_flow_id("superseded")).status == "pending"  # type: ignore[union-attr]
        assert await repo.current_device_slot_flow_id() == "replacement"


@pytest.mark.asyncio
async def test_non_originating_complete_reports_without_polling(monkeypatch):
    async with SessionLocal() as session:
        await OAuthFlowRepository(session, TokenEncryptor()).create(
            OAuthFlowRecord(
                flow_id="remote-device",
                method="device",
                status="pending",
                device_auth_id="auth",
                user_code="code",
                interval_seconds=5,
                expires_at=utcnow() + timedelta(minutes=1),
            )
        )

    replica = _service(oauth_module.OAuthStateStore())
    ensure_poll = AsyncMock(side_effect=AssertionError("non-origin replica started polling"))
    monkeypatch.setattr(replica, "_ensure_device_poll_task_locked", ensure_poll)
    result = await replica.complete_oauth(OauthCompleteRequest(flow_id="remote-device"))
    assert result.status == "pending"
    ensure_poll.assert_not_awaited()
    async with replica._store.lock:
        local = replica._store.get_flow_locked("remote-device")
        assert local is not None
        assert local.poll_task is None
