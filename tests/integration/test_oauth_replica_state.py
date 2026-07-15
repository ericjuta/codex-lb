from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from aiohttp.test_utils import make_mocked_request

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


def test_timezone_aware_pending_expiry_is_normalized():
    now = utcnow()
    live = cast(
        OAuthFlowState,
        SimpleNamespace(
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )
    expired = cast(
        OAuthFlowState,
        SimpleNamespace(
            status="pending",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        ),
    )

    assert not OAuthFlowRepository._is_expired_pending(live, now)
    assert OAuthFlowRepository._is_expired_pending(expired, now)


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
        assert await repo.has_pending_browser_flows()

        assert await repo.set_status("flow-live", status="success", error_message=None)
        assert not await repo.has_pending_browser_flows()
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
        assert not await repo.has_pending_browser_flows()

        await repo.claim_device_slot("device-old")
        await repo.claim_device_slot("device-current")
        assert await repo.current_device_slot_flow_id() == "device-current"
        assert not await repo.consume_device_slot("device-old")
        assert await repo.consume_device_slot("device-current")


@pytest.mark.asyncio
async def test_monotonic_success_is_atomic_across_sessions():
    encryptor = TokenEncryptor()
    async with SessionLocal() as seed_session:
        await OAuthFlowRepository(seed_session, encryptor).create(
            OAuthFlowRecord(
                flow_id="cross-session-race",
                method="device",
                status="pending",
                expires_at=utcnow() + timedelta(minutes=5),
            )
        )

    async with SessionLocal() as winning_session, SessionLocal() as losing_session:
        winner = OAuthFlowRepository(winning_session, encryptor)
        loser = OAuthFlowRepository(losing_session, encryptor)
        stale = await losing_session.get(OAuthFlowState, "cross-session-race")
        assert stale is not None and stale.status == "pending"

        assert await winner.set_status(
            "cross-session-race",
            status="success",
            error_message=None,
        )
        assert not await loser.set_status(
            "cross-session-race",
            status="error",
            error_message="late loser",
        )

    async with SessionLocal() as verify_session:
        record = await OAuthFlowRepository(verify_session, encryptor).get_by_flow_id("cross-session-race")
        assert record is not None and record.status == "success"


@pytest.mark.asyncio
async def test_completion_claim_has_one_cross_session_winner():
    encryptor = TokenEncryptor()
    async with SessionLocal() as session:
        await OAuthFlowRepository(session, encryptor).create(
            OAuthFlowRecord(
                flow_id="completion-claim-race",
                method="browser",
                status="pending",
                expires_at=utcnow() + timedelta(minutes=5),
            )
        )

    async def claim() -> bool:
        async with SessionLocal() as session:
            return await OAuthFlowRepository(session, encryptor).claim_completion("completion-claim-race")

    claims = await asyncio.gather(claim(), claim())
    assert sorted(claims) == [False, True]
    async with SessionLocal() as session:
        record = await OAuthFlowRepository(session, encryptor).get_by_flow_id("completion-claim-race")
        assert record is not None and record.status == "completing"


@pytest.mark.asyncio
async def test_account_persistence_failure_compensates_owned_completion(monkeypatch):
    store = oauth_module.OAuthStateStore()
    replica = _service(store)
    expires_at = utcnow() + timedelta(minutes=5)
    async with SessionLocal() as session:
        await OAuthFlowRepository(session, TokenEncryptor()).create(
            OAuthFlowRecord(
                flow_id="completion-compensation",
                method="browser",
                status="pending",
                expires_at=expires_at,
            )
        )
    async with store.lock:
        store.remember_flow_locked(
            oauth_module.OAuthState(
                flow_id="completion-compensation",
                method="browser",
                status="pending",
                expires_at=expires_at.timestamp(),
            )
        )

    monkeypatch.setattr(
        replica,
        "_persist_tokens",
        AsyncMock(side_effect=RuntimeError("account write failed")),
    )
    with pytest.raises(RuntimeError, match="account write failed"):
        await replica._complete_with_tokens(
            OAuthTokens("access", "refresh", "id"),
            "completion-compensation",
        )

    async with SessionLocal() as session:
        record = await OAuthFlowRepository(session, TokenEncryptor()).get_by_flow_id("completion-compensation")
        assert record is not None
        assert record.status == "error"
        assert record.error_message == "OAuth account persistence failed."
    async with store.lock:
        local = store.get_flow_locked("completion-compensation")
        assert local is not None and local.status == "error"


@pytest.mark.asyncio
async def test_rejected_success_finalization_does_not_publish_local_success(monkeypatch):
    store = oauth_module.OAuthStateStore()
    replica = _service(store)
    expires_at = utcnow() + timedelta(minutes=5)
    async with store.lock:
        store.remember_flow_locked(
            oauth_module.OAuthState(
                flow_id="missing-success-row",
                method="browser",
                status="pending",
                expires_at=expires_at.timestamp(),
            )
        )

    persist_status = AsyncMock(return_value=False)
    monkeypatch.setattr(replica, "_persist_flow_status", persist_status)

    assert not await replica._set_success("missing-success-row")
    persist_status.assert_awaited_once_with(
        "missing-success-row",
        status="success",
        error_message=None,
        expected_status="completing",
    )
    async with store.lock:
        assert store.get_flow_locked("missing-success-row") is None


@pytest.mark.asyncio
async def test_unscoped_status_and_complete_reconcile_current_flow_from_durable_state():
    store = oauth_module.OAuthStateStore()
    replica = _service(store)
    expires_at = utcnow() + timedelta(minutes=5)
    async with SessionLocal() as session:
        repo = OAuthFlowRepository(session, TokenEncryptor())
        await repo.create(
            OAuthFlowRecord(
                flow_id="implicit-current",
                method="browser",
                status="pending",
                expires_at=expires_at,
            )
        )
        assert await repo.set_status("implicit-current", status="success", error_message=None)

    async with store.lock:
        store.remember_flow_locked(
            oauth_module.OAuthState(
                flow_id="implicit-current",
                method="browser",
                status="pending",
                expires_at=expires_at.timestamp(),
            )
        )

    assert (await replica.oauth_status()).status == "success"

    async with store.lock:
        stale = store.get_flow_locked("implicit-current")
        assert stale is not None
        stale.status = "pending"
        store.set_latest_flow_locked(stale)

    assert (await replica.complete_oauth()).status == "success"


@pytest.mark.parametrize(
    "entry_point",
    ["status", "complete", "manual_callback", "handle_callback"],
)
@pytest.mark.asyncio
async def test_all_browser_entry_points_honor_durable_terminal_state(monkeypatch, entry_point):
    expires_at = utcnow() + timedelta(minutes=5)
    state_token = f"state-{entry_point}"
    flow_id = f"terminal-{entry_point}"
    store = oauth_module.OAuthStateStore()
    replica = _service(store)
    exchange = AsyncMock(side_effect=AssertionError("terminal flow replayed authorization code"))
    monkeypatch.setattr(oauth_module, "exchange_authorization_code", exchange)

    async with SessionLocal() as session:
        repo = OAuthFlowRepository(session, TokenEncryptor())
        await repo.create(
            OAuthFlowRecord(
                flow_id=flow_id,
                method="browser",
                status="pending",
                state_token=state_token,
                code_verifier="verifier",
                expires_at=expires_at,
            )
        )
        assert await repo.set_status(flow_id, status="success", error_message=None)

    async with store.lock:
        store.remember_flow_locked(
            oauth_module.OAuthState(
                flow_id=flow_id,
                method="browser",
                status="pending",
                state_token=state_token,
                code_verifier="verifier",
                expires_at=expires_at.timestamp(),
            )
        )

    if entry_point == "status":
        assert (await replica.oauth_status(flow_id)).status == "success"
    elif entry_point == "complete":
        result = await replica.complete_oauth(OauthCompleteRequest(flow_id=flow_id))
        assert result.status == "success"
    elif entry_point == "manual_callback":
        result = await replica.manual_callback(
            f"http://localhost:1455/auth/callback?code=replay&state={state_token}",
            flow_id=flow_id,
        )
        assert result.status == "success"
    else:
        request = make_mocked_request(
            "GET",
            f"/auth/callback?code=replay&state={state_token}",
        )
        response = await replica._handle_callback(request)
        assert response.status == 200
        assert response.text is not None and "Login failed" not in response.text

    exchange.assert_not_awaited()
    async with store.lock:
        local = store.get_flow_locked(flow_id)
        assert local is not None and local.status == "success"


@pytest.mark.asyncio
async def test_durable_remote_browser_flow_keeps_local_callback_listener_active():
    store = oauth_module.OAuthStateStore()
    replica = _service(store)
    fake_server = cast(oauth_module.OAuthCallbackServer, SimpleNamespace(stop=AsyncMock()))

    async with SessionLocal() as session:
        await OAuthFlowRepository(session, TokenEncryptor()).create(
            OAuthFlowRecord(
                flow_id="remote-browser",
                method="browser",
                status="pending",
                expires_at=utcnow() + timedelta(minutes=5),
            )
        )
    async with store.lock:
        store._callback_server = fake_server

    await replica._stop_callback_server_if_idle()

    fake_server.stop.assert_not_awaited()
    async with store.lock:
        assert store._callback_server is fake_server


@pytest.mark.asyncio
async def test_remote_browser_flow_created_during_stop_restarts_listener(monkeypatch):
    store = oauth_module.OAuthStateStore()
    replica = _service(store)
    stop_started = asyncio.Event()
    release_stop = asyncio.Event()
    replacements: list[object] = []

    class StoppingServer:
        async def stop(self) -> None:
            stop_started.set()
            await release_stop.wait()

    class ReplacementServer:
        def __init__(self, *_args, **_kwargs) -> None:
            self.started = False
            replacements.append(self)

        async def start(self) -> None:
            self.started = True

        async def stop(self) -> None:
            return None

    monkeypatch.setattr(oauth_module, "OAuthCallbackServer", ReplacementServer)
    async with store.lock:
        store._callback_server = cast(oauth_module.OAuthCallbackServer, StoppingServer())

    stop_task = asyncio.create_task(replica._stop_callback_server_if_idle())
    await asyncio.wait_for(stop_started.wait(), timeout=2)
    async with SessionLocal() as session:
        await OAuthFlowRepository(session, TokenEncryptor()).create(
            OAuthFlowRecord(
                flow_id="created-during-stop",
                method="browser",
                status="pending",
                expires_at=utcnow() + timedelta(minutes=5),
            )
        )
    release_stop.set()
    await asyncio.wait_for(stop_task, timeout=2)

    assert len(replacements) == 1
    replacement = replacements[0]
    assert replacement.started  # type: ignore[attr-defined]
    async with store.lock:
        assert store._callback_server is replacement


@pytest.mark.asyncio
async def test_existing_account_start_uses_durable_listener_guard():
    store = oauth_module.OAuthStateStore()

    @asynccontextmanager
    async def repo_factory():
        async with SessionLocal() as session:
            yield AccountsRepository(session)

    accounts = cast(
        AccountsRepository,
        SimpleNamespace(list_accounts=AsyncMock(return_value=[object()])),
    )
    replica = oauth_module.OauthService(accounts, repo_factory=repo_factory, store=store)
    fake_server = cast(oauth_module.OAuthCallbackServer, SimpleNamespace(stop=AsyncMock()))
    async with SessionLocal() as session:
        await OAuthFlowRepository(session, TokenEncryptor()).create(
            OAuthFlowRecord(
                flow_id="remote-existing-account",
                method="browser",
                status="pending",
                expires_at=utcnow() + timedelta(minutes=5),
            )
        )
    async with store.lock:
        store._callback_server = fake_server

    response = await replica.start_oauth(OauthStartRequest())

    assert response.method == "browser"
    fake_server.stop.assert_not_awaited()
    async with store.lock:
        assert store._callback_server is fake_server


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


@pytest.mark.parametrize("path", ["manual_callback", "handle_callback"])
@pytest.mark.asyncio
async def test_callback_loser_reports_durable_success(monkeypatch, path):
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
    if path == "manual_callback":
        result = await replica.manual_callback(
            f"http://localhost:1455/auth/callback?code=race&state={state}",
            flow_id=started.flow_id,
        )
        assert result.status == "success"
    else:
        request = make_mocked_request(
            "GET",
            f"/auth/callback?code=race&state={state}",
        )
        response = await replica._handle_callback(request)
        assert response.status == 200
        assert response.text is not None and "Login failed" not in response.text
    async with replica._store.lock:
        local = replica._store.get_flow_locked(started.flow_id)
        assert local is not None
        assert local.status == "success"


@pytest.mark.parametrize("path", ["manual_callback", "handle_callback"])
@pytest.mark.asyncio
async def test_callback_purge_race_saves_no_uncoordinated_account(monkeypatch, path):
    async def no_callback_server(self) -> None:
        del self

    async def no_route():
        return None

    monkeypatch.setattr(oauth_module.OAuthCallbackServer, "start", no_callback_server)
    monkeypatch.setattr(oauth_module, "_oauth_route", no_route)
    replica = _service(oauth_module.OAuthStateStore())
    persist_tokens = AsyncMock()
    monkeypatch.setattr(replica, "_persist_tokens", persist_tokens)
    started = await replica.start_oauth(OauthStartRequest(force_method="browser"))
    assert started.flow_id is not None
    assert started.authorization_url is not None
    state = _state_token(started.authorization_url)

    async def exchange_after_purge(**_kwargs):
        async with SessionLocal() as session:
            row = await session.get(OAuthFlowState, started.flow_id)
            assert row is not None
            await session.delete(row)
            await session.commit()
        return OAuthTokens("access", "refresh", "id")

    monkeypatch.setattr(oauth_module, "exchange_authorization_code", exchange_after_purge)
    if path == "manual_callback":
        result = await replica.manual_callback(
            f"http://localhost:1455/auth/callback?code=race&state={state}",
            flow_id=started.flow_id,
        )
        assert result.status == "error"
    else:
        request = make_mocked_request(
            "GET",
            f"/auth/callback?code=race&state={state}",
        )
        response = await replica._handle_callback(request)
        assert response.status == 200
        assert response.text is not None and "Login failed" in response.text

    persist_tokens.assert_not_awaited()
    async with replica._store.lock:
        assert replica._store.get_flow_locked(started.flow_id) is None


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
async def test_overlapping_same_replica_device_starts_preserve_later_owner(monkeypatch):
    async def fake_device_code(**_kwargs):
        return DeviceCode(
            verification_url="https://example.invalid/device",
            user_code="overlap-code",
            device_auth_id="overlap-auth",
            interval_seconds=60,
            expires_in_seconds=300,
        )

    monkeypatch.setattr(oauth_module, "request_device_code", fake_device_code)
    monkeypatch.setattr(oauth_module, "_oauth_route", AsyncMock(return_value=None))
    replica = _service(oauth_module.OAuthStateStore())
    poll_started: list[str | None] = []

    def record_poller(state):
        poll_started.append(state.flow_id)
        return True

    monkeypatch.setattr(replica, "_ensure_device_poll_task_locked", record_poller)
    original_persist = replica._persist_flow_record
    first_persist_reached = asyncio.Event()
    release_first_persist = asyncio.Event()
    persist_calls = 0

    async def gated_persist(record):
        nonlocal persist_calls
        persist_calls += 1
        if persist_calls == 1:
            first_persist_reached.set()
            await release_first_persist.wait()
        await original_persist(record)

    monkeypatch.setattr(replica, "_persist_flow_record", gated_persist)
    first_task = asyncio.create_task(replica.start_oauth(OauthStartRequest(force_method="device")))
    await asyncio.wait_for(first_persist_reached.wait(), timeout=2)
    second = await replica.start_oauth(OauthStartRequest(force_method="device"))
    release_first_persist.set()
    first = await asyncio.wait_for(first_task, timeout=2)

    assert first.flow_id is not None
    assert second.flow_id is not None
    assert first.flow_id != second.flow_id
    async with SessionLocal() as session:
        current = await OAuthFlowRepository(
            session,
            TokenEncryptor(),
        ).current_device_slot_flow_id()
    assert current == second.flow_id
    assert poll_started == [second.flow_id]
    async with replica._store.lock:
        stale = replica._store.get_flow_locked(first.flow_id)
        assert stale is None or stale.poll_task is None


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
async def test_device_purge_race_saves_no_uncoordinated_account(monkeypatch):
    replica = _service(oauth_module.OAuthStateStore())
    expires_at = utcnow() + timedelta(minutes=1)
    flow = oauth_module.OAuthState(
        flow_id="device-purge-race",
        method="device",
        status="pending",
        device_auth_id="auth",
        user_code="code",
        interval_seconds=0,
        expires_at=expires_at.timestamp(),
    )
    async with replica._store.lock:
        replica._store.remember_flow_locked(flow)
    async with SessionLocal() as session:
        repo = OAuthFlowRepository(session, TokenEncryptor())
        await repo.create(
            OAuthFlowRecord(
                flow_id="device-purge-race",
                method="device",
                status="pending",
                device_auth_id="auth",
                user_code="code",
                expires_at=expires_at,
            )
        )
        await repo.claim_device_slot("device-purge-race")

    async def exchange_after_purge(**_kwargs):
        async with SessionLocal() as session:
            row = await session.get(OAuthFlowState, "device-purge-race")
            assert row is not None
            await session.delete(row)
            await session.commit()
        return OAuthTokens("access", "refresh", "id")

    monkeypatch.setattr(oauth_module, "_oauth_route", AsyncMock(return_value=None))
    monkeypatch.setattr(oauth_module, "exchange_device_token", exchange_after_purge)
    persist_tokens = AsyncMock()
    monkeypatch.setattr(replica, "_persist_tokens", persist_tokens)

    await replica._poll_device_tokens(
        "device-purge-race",
        oauth_module.DevicePollContext(
            device_auth_id="auth",
            user_code="code",
            interval_seconds=0,
            expires_at=expires_at.timestamp(),
        ),
    )

    persist_tokens.assert_not_awaited()
    async with replica._store.lock:
        assert replica._store.get_flow_locked("device-purge-race") is None


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

    async with SessionLocal() as session:
        assert await OAuthFlowRepository(session, TokenEncryptor()).set_status(
            "remote-device",
            status="success",
            error_message=None,
        )
    terminal = await replica.complete_oauth(OauthCompleteRequest(flow_id="remote-device"))
    assert terminal.status == "success"
    ensure_poll.assert_not_awaited()
