"""Tests for transient stream retry logic.

Covers:
- Streaming: SSE-level transient errors → same-account retry → failover
- Streaming: HTTP-level 500 → same-account retry → failover
- Compact: HTTP 500 → same-account retry with backoff → account failover
- Budget exhaustion during inner retry
- Non-500 errors are not intercepted by transient retry
"""

from __future__ import annotations

import base64
import json

import aiohttp
import pytest
from sqlalchemy import select

import app.modules.proxy.service as proxy_module
from app.core.auth import generate_unique_account_id
from app.core.clients.proxy import ProxyResponseError
from app.core.errors import openai_error
from app.core.openai.models import CompactResponsePayload
from app.core.utils.request_id import get_request_id
from app.db.models import Account, AccountStatus, ApiKeyUsageReservation
from app.db.session import SessionLocal
from app.modules.proxy.load_balancer import LoadBalancer

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _force_usage_weighted_routing(async_client) -> None:
    current = await async_client.get("/api/settings")
    assert current.status_code == 200
    payload = current.json()
    payload["routingStrategy"] = "usage_weighted"
    response = await async_client.put("/api/settings", json=payload)
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _encode_jwt(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    return f"header.{body}.sig"


def _make_auth_json(account_id: str, email: str) -> dict:
    payload = {
        "email": email,
        "chatgpt_account_id": account_id,
        "https://api.openai.com/auth": {"chatgpt_plan_type": "plus"},
    }
    return {
        "tokens": {
            "idToken": _encode_jwt(payload),
            "accessToken": "access-token",
            "refreshToken": "refresh-token",
            "accountId": account_id,
        },
    }


async def _import_account(async_client, account_id: str, email: str) -> str:
    auth_json = _make_auth_json(account_id, email)
    files = {"auth_json": ("auth.json", json.dumps(auth_json), "application/json")}
    response = await async_client.post("/api/accounts/import", files=files)
    assert response.status_code == 200
    return generate_unique_account_id(account_id, email)


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _server_error_sse_event() -> str:
    return _sse_event(
        {
            "type": "response.failed",
            "response": {
                "error": {
                    "code": "server_error",
                    "message": "An error occurred while processing your request.",
                },
            },
        }
    )


def _overload_sse_event(error_code: str) -> str:
    return _sse_event(
        {
            "type": "response.failed",
            "response": {
                "error": {
                    "code": error_code,
                    "message": "Our servers are currently overloaded. Please try again later.",
                },
            },
        }
    )


def _stream_timeout_sse_event() -> str:
    return _sse_event(
        {
            "type": "response.failed",
            "response": {
                "error": {
                    "code": "upstream_request_timeout",
                    "message": "Proxy request budget exhausted",
                },
            },
        }
    )


def _model_capacity_sse_event() -> str:
    return _sse_event(
        {
            "type": "response.failed",
            "response": {
                "error": {
                    "code": "invalid_request_error",
                    "message": "Selected model is at capacity. Please try a different model.",
                },
            },
        }
    )


def _success_sse_event(response_id: str = "resp_ok") -> str:
    return _sse_event(
        {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        }
    )


def _extract_events(lines: list[str]) -> list[dict]:
    events = []
    for line in lines:
        if line.startswith("data: "):
            data = line[6:]
            if data == "[DONE]":
                continue
            events.append(json.loads(data))
    return events


# ===========================================================================
# Streaming — SSE-level server_error
# ===========================================================================


@pytest.mark.asyncio
async def test_stream_server_error_surfaces_without_replay(async_client, monkeypatch):
    """An upstream terminal server error cannot prove that retrying the POST is safe."""
    await _import_account(async_client, "acc_trans_1", "trans1@example.com")

    call_count = 0
    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        nonlocal call_count
        call_count += 1
        seen_account_ids.append(account_id)
        if call_count == 1:
            yield _server_error_sse_event()
            return
        yield _success_sse_event()

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    failed = [event for event in events if event.get("type") == "response.failed"]
    assert len(failed) == 1
    assert failed[0]["response"]["error"]["code"] == "server_error"
    assert seen_account_ids == ["acc_trans_1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("error_code", ["overloaded_error", "server_is_overloaded"])
async def test_stream_overload_alias_surfaces_without_replay(async_client, monkeypatch, error_code):
    await _import_account(async_client, f"acc_{error_code}", f"{error_code}@example.com")

    call_count = 0
    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        nonlocal call_count
        call_count += 1
        seen_account_ids.append(account_id)
        if call_count == 1:
            yield _overload_sse_event(error_code)
            return
        yield _success_sse_event("resp_server_overloaded_ok")

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    failed = [event for event in events if event.get("type") == "response.failed"]
    assert len(failed) == 1
    assert failed[0]["response"]["error"]["code"] == error_code
    assert seen_account_ids == [f"acc_{error_code}"]


@pytest.mark.asyncio
async def test_stream_timeout_surfaces_without_replay(async_client, monkeypatch):
    """An upstream terminal timeout is not proven pre-dispatch work."""
    await _import_account(async_client, "acc_trans_timeout", "timeout@example.com")

    call_count = 0
    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        nonlocal call_count
        call_count += 1
        seen_account_ids.append(account_id)
        if call_count == 1:
            yield _stream_timeout_sse_event()
            return
        yield _success_sse_event()

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    failed = [e for e in events if e.get("type") == "response.failed"]
    assert len(failed) == 1
    assert failed[0]["response"]["error"]["code"] == "upstream_request_timeout"
    assert seen_account_ids == ["acc_trans_timeout"]


@pytest.mark.asyncio
async def test_stream_model_capacity_without_response_id_surfaces_without_replay(async_client, monkeypatch):
    """An upstream terminal event is accepted work even when it omits a response id."""
    await _import_account(async_client, "acc_model_capacity_retry", "model-capacity@example.com")

    call_count = 0
    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        nonlocal call_count
        call_count += 1
        seen_account_ids.append(account_id)
        if call_count == 1:
            yield _model_capacity_sse_event()
            return

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    failed = [event for event in events if event.get("type") == "response.failed"]
    assert len(failed) == 1
    assert failed[0]["response"]["error"]["code"] == "invalid_request_error"
    assert seen_account_ids == ["acc_model_capacity_retry"]


@pytest.mark.asyncio
async def test_stream_raw_capacity_error_with_proxy_request_id_surfaces_without_replay(async_client, monkeypatch):
    """A terminal upstream error remains terminal even with a proxy-generated id."""
    await _import_account(async_client, "acc_raw_model_capacity_retry", "raw-model-capacity@example.com")

    call_count = 0
    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        nonlocal call_count
        call_count += 1
        seen_account_ids.append(account_id)
        if call_count == 1:
            yield _sse_event(
                {
                    "type": "error",
                    "code": "invalid_request_error",
                    "message": "Selected model is at capacity. Please try a different model.",
                }
            )
            return

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    errors = [event for event in events if event.get("type") == "error"]
    assert len(errors) == 1
    assert errors[0]["code"] == "invalid_request_error"
    assert seen_account_ids == ["acc_raw_model_capacity_retry"]


@pytest.mark.asyncio
async def test_stream_model_capacity_top_level_response_id_surfaces_without_replay(async_client, monkeypatch):
    """A top-level upstream response_id proves dispatch, so capacity errors must not be replayed."""
    await _import_account(async_client, "acc_model_capacity_accepted", "model-capacity-accepted@example.com")

    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        yield _sse_event(
            {
                "type": "response.failed",
                "response_id": "resp_model_capacity_accepted",
                "response": {
                    "error": {
                        "code": "invalid_request_error",
                        "message": "Selected model is at capacity. Please try a different model.",
                    },
                },
            }
        )

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    failed = [event for event in events if event.get("type") == "response.failed"]
    assert len(failed) == 1
    assert failed[0]["response"]["error"]["code"] == "invalid_request_error"
    assert seen_account_ids == ["acc_model_capacity_accepted"]


@pytest.mark.asyncio
async def test_stream_empty_upstream_body_surfaces_without_replay(async_client, monkeypatch):
    """An untyped empty upstream stream may be post-dispatch, so it is not replayed."""
    await _import_account(async_client, "acc_empty_body_no_replay", "empty-body-no-replay@example.com")

    call_count = 0
    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        nonlocal call_count
        call_count += 1
        seen_account_ids.append(account_id)
        if call_count == 1:
            if False:
                yield ""
            return

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    error_codes = [event["response"]["error"]["code"] for event in events if event.get("type") == "response.failed"]
    assert error_codes[-1] == "stream_incomplete"
    assert seen_account_ids == ["acc_empty_body_no_replay"]


@pytest.mark.asyncio
async def test_stream_body_read_client_error_surfaces_without_replay(async_client, monkeypatch):
    """Post-connect body-read errors are not replayed because upstream delivery is uncertain."""
    await _import_account(async_client, "acc_previsible_disconnect_a", "previsible-disconnect-a@example.com")
    await _import_account(async_client, "acc_previsible_disconnect_b", "previsible-disconnect-b@example.com")

    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        if False:
            yield ""
        raise aiohttp.ServerDisconnectedError("Server disconnected")

    async def fake_sleep(delay: float) -> None:
        pass

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)
    monkeypatch.setattr(proxy_module.asyncio, "sleep", fake_sleep)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    error_codes = [event["response"]["error"]["code"] for event in events if event.get("type") == "response.failed"]
    assert error_codes[-1] == "upstream_unavailable"
    assert "no_accounts" not in error_codes
    assert seen_account_ids == ["acc_previsible_disconnect_a"]


@pytest.mark.asyncio
async def test_stream_serialized_body_read_disconnect_with_response_id_surfaces_without_replay(
    async_client, monkeypatch
):
    """Serialized post-dispatch body-read failures with response_id are not safe to replay."""
    await _import_account(async_client, "acc_serialized_disconnect_a", "serialized-disconnect-a@example.com")
    await _import_account(async_client, "acc_serialized_disconnect_b", "serialized-disconnect-b@example.com")

    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        yield _sse_event(
            {
                "type": "response.failed",
                "response_id": "resp_serialized_disconnect",
                "response": {
                    "error": {
                        "code": "upstream_unavailable",
                        "message": "Server disconnected",
                    },
                },
            }
        )

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    failed = [event for event in events if event.get("type") == "response.failed"]
    assert len(failed) == 1
    assert failed[0]["response"]["error"]["code"] == "upstream_unavailable"
    assert seen_account_ids == ["acc_serialized_disconnect_a"]


@pytest.mark.asyncio
async def test_stream_serialized_body_read_disconnect_with_request_id_surfaces_without_replay(
    async_client, monkeypatch
):
    """A response.failed using the proxy request id still represents an unsafe post-dispatch failure."""
    await _import_account(async_client, "acc_serialized_request_id_disconnect_a", "serialized-request-a@example.com")
    await _import_account(async_client, "acc_serialized_request_id_disconnect_b", "serialized-request-b@example.com")

    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        del payload, headers, access_token, base_url, raise_for_status
        seen_account_ids.append(account_id)
        request_id = get_request_id()
        assert request_id is not None
        yield _sse_event(
            {
                "type": "response.failed",
                "response": {
                    "id": request_id,
                    "error": {
                        "code": "upstream_unavailable",
                        "message": "Server disconnected",
                    },
                },
            }
        )

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    failed = [event for event in events if event.get("type") == "response.failed"]
    assert len(failed) == 1
    assert failed[0]["response"]["error"]["code"] == "upstream_unavailable"
    assert seen_account_ids == ["acc_serialized_request_id_disconnect_a"]


@pytest.mark.asyncio
async def test_stream_pinned_previsible_close_exhaustion_surfaces_stream_incomplete(async_client, monkeypatch):
    """Pinned previous-response EOF cannot fail over, so preserve the stream failure for the client."""
    upstream_account_id = "acc_pinned_previsible_close"
    owner_account_id = await _import_account(
        async_client,
        upstream_account_id,
        "pinned-previsible-close@example.com",
    )

    seen_account_ids: list[str | None] = []

    async def fake_owner(self, *, previous_response_id, api_key, session_id=None, surface):
        del self, previous_response_id, api_key, session_id, surface
        return owner_account_id

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        if False:
            yield ""
        return

    async def fake_sleep(delay: float) -> None:
        pass

    monkeypatch.setattr(proxy_module.ProxyService, "_resolve_websocket_previous_response_owner", fake_owner)
    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)
    monkeypatch.setattr(proxy_module.asyncio, "sleep", fake_sleep)

    payload = {
        "model": "gpt-5.1",
        "instructions": "hi",
        "input": [],
        "stream": True,
        "previous_response_id": "resp_pinned_previsible_close",
    }
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    error_codes = [event["response"]["error"]["code"] for event in events if event.get("type") == "response.failed"]
    assert error_codes[-1] == "stream_incomplete"
    assert "previous_response_owner_unavailable" not in error_codes
    assert set(seen_account_ids) == {upstream_account_id}


@pytest.mark.asyncio
async def test_stream_server_error_does_not_fail_over_after_accepted_terminal_event(async_client, monkeypatch):
    """A terminal event stays on its first account even when another account is eligible."""
    await _import_account(async_client, "acc_trans_fo_a", "fo_a@example.com")
    await _import_account(async_client, "acc_trans_fo_b", "fo_b@example.com")

    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        if account_id == "acc_trans_fo_a":
            yield _server_error_sse_event()
            return
        yield _success_sse_event()

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    failed = [event for event in events if event.get("type") == "response.failed"]
    assert len(failed) == 1
    assert failed[0]["response"]["error"]["code"] == "server_error"
    assert seen_account_ids == ["acc_trans_fo_a"]


@pytest.mark.asyncio
async def test_stream_server_error_all_accounts_exhausted(async_client, monkeypatch):
    """server_error on all accounts → eventually returns error to client."""
    await _import_account(async_client, "acc_trans_all_a", "all_a@example.com")

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        yield _server_error_sse_event()

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    # Should end with an error event (either response.failed or no_accounts)
    last_event = events[-1] if events else {}
    assert last_event.get("type") in ("response.failed", "error")


@pytest.mark.asyncio
async def test_stream_server_error_does_not_make_a_third_post(async_client, monkeypatch):
    """An accepted terminal event prevents follow-up same-account POSTs."""
    await _import_account(async_client, "acc_trans_3rd", "trans3@example.com")

    call_count = 0
    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        nonlocal call_count
        call_count += 1
        seen_account_ids.append(account_id)
        if call_count <= 2:
            yield _server_error_sse_event()
            return
        yield _success_sse_event()

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    failed = [event for event in events if event.get("type") == "response.failed"]
    assert len(failed) == 1
    assert failed[0]["response"]["error"]["code"] == "server_error"
    assert seen_account_ids == ["acc_trans_3rd"]


# ===========================================================================
# Streaming — HTTP-level 500 (ProxyResponseError)
# ===========================================================================


@pytest.mark.asyncio
async def test_stream_http_500_retries_same_account_then_succeeds(async_client, monkeypatch):
    """HTTP 500 ProxyResponseError → inner retry on same account → success."""
    await _import_account(async_client, "acc_http500_1", "http500@example.com")

    call_count = 0
    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        nonlocal call_count
        call_count += 1
        seen_account_ids.append(account_id)
        if call_count == 1:
            raise ProxyResponseError(
                500,
                openai_error("server_error", "An error occurred while processing your request."),
                failure_phase="status",
            )
        yield _success_sse_event()

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    completed = [e for e in events if e.get("type") == "response.completed"]
    assert len(completed) == 1

    assert len(seen_account_ids) == 2
    assert seen_account_ids[0] == seen_account_ids[1]


@pytest.mark.asyncio
async def test_stream_http_500_exhausts_then_failover(async_client, monkeypatch):
    """HTTP 500 x3 on account A → failover to account B → success."""
    await _import_account(async_client, "acc_h5fo_a", "h5fo_a@example.com")
    await _import_account(async_client, "acc_h5fo_b", "h5fo_b@example.com")

    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        if account_id == "acc_h5fo_a":
            raise ProxyResponseError(
                500,
                openai_error("server_error", "Internal server error"),
                failure_phase="status",
            )
        yield _success_sse_event()

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    completed = [e for e in events if e.get("type") == "response.completed"]
    assert len(completed) == 1

    a_calls = [aid for aid in seen_account_ids if aid == "acc_h5fo_a"]
    b_calls = [aid for aid in seen_account_ids if aid == "acc_h5fo_b"]
    assert len(a_calls) == 3
    assert len(b_calls) >= 1


@pytest.mark.asyncio
async def test_stream_connect_phase_429_usage_limit_transparent_failover(async_client, monkeypatch):
    """Connect-phase 429/usage_limit_reached on A should fail over to B before any downstream event."""
    await _import_account(async_client, "acc_stream_429_a", "stream429a@example.com")
    await _import_account(async_client, "acc_stream_429_b", "stream429b@example.com")

    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        if account_id == "acc_stream_429_a":
            raise ProxyResponseError(
                429,
                openai_error("usage_limit_reached", "usage limit reached"),
                failure_phase="status",
            )
        yield _success_sse_event("resp_stream_429_ok")

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    completed = [e for e in events if e.get("type") == "response.completed"]
    failed = [e for e in events if e.get("type") == "response.failed"]
    assert len(completed) == 1
    assert len(failed) == 0
    assert seen_account_ids[:2] == ["acc_stream_429_a", "acc_stream_429_b"]


@pytest.mark.asyncio
async def test_stream_http_502_unknown_code_fails_over_to_second_account(async_client, monkeypatch):
    await _import_account(async_client, "acc_h502_a", "h502_a@example.com")
    await _import_account(async_client, "acc_h502_b", "h502_b@example.com")

    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        if account_id == "acc_h502_a":
            raise ProxyResponseError(
                502,
                openai_error("bad_gateway", "Bad gateway"),
                failure_phase="status",
            )
        yield _success_sse_event()

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    completed = [e for e in events if e.get("type") == "response.completed"]
    assert len(completed) == 1
    assert seen_account_ids[:2] == ["acc_h502_a", "acc_h502_b"]


# ===========================================================================
# Streaming — Non-server_error is NOT retried via transient path
# ===========================================================================


@pytest.mark.asyncio
async def test_stream_non_server_error_not_retried_as_transient(async_client, monkeypatch):
    """A 400-class error should NOT be caught by transient retry logic."""
    await _import_account(async_client, "acc_no_trans", "notrans@example.com")

    call_count = 0

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        nonlocal call_count
        call_count += 1
        yield _sse_event(
            {
                "type": "response.failed",
                "response": {
                    "error": {
                        "code": "invalid_request_error",
                        "message": "bad request",
                    },
                },
            }
        )

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    failed = [e for e in events if e.get("type") == "response.failed"]
    assert len(failed) == 1

    # Should NOT retry — only 1 call
    assert call_count == 1


@pytest.mark.asyncio
async def test_stream_rate_limit_on_last_attempt_returns_actual_error(async_client, monkeypatch):
    """rate_limit_exceeded on the final outer attempt must yield the real error event,
    not a generic no_accounts message. Regression test for allow_retry flag separation.

    Needs 3 accounts so each outer attempt (max_attempts=3) reaches _stream_once:
    - Attempt 0: account A → rate_limit → mark A RATE_LIMITED → continue
    - Attempt 1: account B → rate_limit → mark B RATE_LIMITED → continue
    - Attempt 2 (last): account C → rate_limit → allow_retry=False →
      error event yielded to client → _TerminalStreamError → return
    """
    await _import_account(async_client, "acc_rl_a", "rla@example.com")
    await _import_account(async_client, "acc_rl_b", "rlb@example.com")
    await _import_account(async_client, "acc_rl_c", "rlc@example.com")

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        yield _sse_event(
            {
                "type": "response.failed",
                "response": {
                    "error": {
                        "code": "rate_limit_exceeded",
                        "message": "slow down",
                    },
                },
            }
        )

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    # The last event the client sees should contain the actual rate_limit error
    last_event = events[-1] if events else {}
    error = last_event.get("response", {}).get("error", {})
    assert error.get("code") != "no_accounts", "Client received generic no_accounts instead of actual error"


@pytest.mark.asyncio
async def test_stream_mid_stream_error_is_surfaced_without_failover(async_client, monkeypatch):
    """Once bytes/events are emitted downstream, failover is forbidden; surface the mid-stream error."""
    await _import_account(async_client, "acc_midstream_a", "midstreama@example.com")
    await _import_account(async_client, "acc_midstream_b", "midstreamb@example.com")

    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        if account_id == "acc_midstream_a":
            yield _sse_event({"type": "response.in_progress", "response": {"id": "resp_midstream"}})
            yield _sse_event(
                {
                    "type": "response.failed",
                    "response": {"error": {"code": "rate_limit_exceeded", "message": "mid-stream limit"}},
                }
            )
            return
        yield _success_sse_event("resp_should_not_happen")

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    failed = [e for e in events if e.get("type") == "response.failed"]
    completed = [e for e in events if e.get("type") == "response.completed"]
    assert len(failed) == 1
    assert failed[0].get("response", {}).get("error", {}).get("code") == "rate_limit_exceeded"
    assert len(completed) == 0
    assert seen_account_ids == ["acc_midstream_a"]


@pytest.mark.asyncio
async def test_stream_http_500_after_text_is_surfaced_without_same_account_replay(async_client, monkeypatch):
    """A transport/status exception after visible text must not restart the answer on retry."""
    await _import_account(async_client, "acc_midtext_500", "midtext500@example.com")

    call_count = 0

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        nonlocal call_count
        call_count += 1
        yield _sse_event({"type": "response.output_text.delta", "delta": "partial answer"})
        raise ProxyResponseError(
            500,
            openai_error("server_error", "late server error"),
            failure_phase="body",
        )

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    deltas = [e for e in events if e.get("type") == "response.output_text.delta"]
    failed = [e for e in events if e.get("type") == "response.failed"]
    completed = [e for e in events if e.get("type") == "response.completed"]
    assert [e.get("delta") for e in deltas] == ["partial answer"]
    assert len(failed) == 1
    assert failed[0].get("response", {}).get("error", {}).get("code") == "server_error"
    assert completed == []
    assert call_count == 1


@pytest.mark.asyncio
async def test_stream_http_429_after_text_is_surfaced_without_account_failover(async_client, monkeypatch):
    """A quota/rate-limit exception after visible text cannot be hidden by replaying on another account."""
    await _import_account(async_client, "acc_midtext_429_a", "midtext429a@example.com")
    await _import_account(async_client, "acc_midtext_429_b", "midtext429b@example.com")

    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        if account_id == "acc_midtext_429_a":
            yield _sse_event({"type": "response.output_text.delta", "delta": "visible"})
            raise ProxyResponseError(
                429,
                openai_error("usage_limit_reached", "usage limit reached"),
                failure_phase="body",
            )
        yield _success_sse_event("resp_should_not_replay")

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    deltas = [e for e in events if e.get("type") == "response.output_text.delta"]
    failed = [e for e in events if e.get("type") == "response.failed"]
    completed = [e for e in events if e.get("type") == "response.completed"]
    assert [e.get("delta") for e in deltas] == ["visible"]
    assert len(failed) == 1
    assert failed[0].get("response", {}).get("error", {}).get("code") == "usage_limit_reached"
    assert completed == []
    assert seen_account_ids == ["acc_midtext_429_a"]


@pytest.mark.asyncio
async def test_v1_responses_non_streaming_500_preserves_http_status(async_client, monkeypatch):
    """Non-streaming /v1/responses uses propagate_http_errors=True.
    After exhausting transient retries, the HTTP 500 status must be preserved
    (not swallowed into a generic SSE error)."""
    await _import_account(async_client, "acc_prop_500", "prop500@example.com")

    call_count = 0

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        nonlocal call_count
        call_count += 1
        raise ProxyResponseError(
            500,
            openai_error("server_error", "An error occurred while processing your request."),
            failure_phase="status",
        )
        yield ""  # make it a generator  # pragma: no cover

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "input": "hi"}
    response = await async_client.post("/v1/responses", json=payload)
    # Must preserve the upstream 500, not 503/502
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "server_error"
    # Should have retried on same account before giving up
    assert call_count == 3


# ===========================================================================
# Compact — HTTP 500 retry
# ===========================================================================


@pytest.mark.asyncio
async def test_compact_500_succeeds_on_second_try_same_account(async_client, monkeypatch):
    """Compact 500 on 1st call → backoff retry → success on 2nd, same account."""
    await _import_account(async_client, "acc_c500_1", "c500@example.com")

    call_count = 0
    seen_account_ids: list[str | None] = []

    async def fake_compact(payload, headers, access_token, account_id):
        nonlocal call_count
        call_count += 1
        seen_account_ids.append(account_id)
        if call_count == 1:
            raise ProxyResponseError(
                500,
                openai_error("server_error", "An error occurred while processing your request."),
                failure_phase="status",
                retryable_same_contract=True,
            )
        return CompactResponsePayload.model_validate({"object": "response.compaction", "output": []})

    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": []}
    response = await async_client.post("/backend-api/codex/responses/compact", json=payload)
    assert response.status_code == 200
    assert response.json()["object"] == "response.compaction"

    assert len(seen_account_ids) == 2
    assert seen_account_ids[0] == seen_account_ids[1]


@pytest.mark.asyncio
async def test_compact_500_succeeds_on_third_try(async_client, monkeypatch):
    """Compact 500 x2, success on 3rd — all same account."""
    await _import_account(async_client, "acc_c500_3", "c500_3@example.com")

    call_count = 0
    seen_account_ids: list[str | None] = []

    async def fake_compact(payload, headers, access_token, account_id):
        nonlocal call_count
        call_count += 1
        seen_account_ids.append(account_id)
        if call_count <= 2:
            raise ProxyResponseError(
                500,
                openai_error("server_error", "server error"),
                failure_phase="status",
                retryable_same_contract=True,
            )
        return CompactResponsePayload.model_validate({"object": "response.compaction", "output": []})

    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": []}
    response = await async_client.post("/backend-api/codex/responses/compact", json=payload)
    assert response.status_code == 200

    assert len(seen_account_ids) == 3
    assert len(set(seen_account_ids)) == 1


@pytest.mark.asyncio
async def test_compact_500_exhausts_retries_then_failover(async_client, monkeypatch):
    """Compact 500 x3 on account A → failover → success on account B."""
    await _import_account(async_client, "acc_cfo_a", "cfo_a@example.com")
    await _import_account(async_client, "acc_cfo_b", "cfo_b@example.com")

    seen_account_ids: list[str | None] = []

    async def fake_compact(payload, headers, access_token, account_id):
        seen_account_ids.append(account_id)
        if account_id == "acc_cfo_a":
            raise ProxyResponseError(
                500,
                openai_error("server_error", "server error"),
                failure_phase="status",
                retryable_same_contract=True,
            )
        return CompactResponsePayload.model_validate({"object": "response.compaction", "output": []})

    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": []}
    response = await async_client.post("/backend-api/codex/responses/compact", json=payload)
    assert response.status_code == 200

    a_calls = [aid for aid in seen_account_ids if aid == "acc_cfo_a"]
    b_calls = [aid for aid in seen_account_ids if aid == "acc_cfo_b"]
    assert len(a_calls) == 3
    assert len(b_calls) >= 1


@pytest.mark.asyncio
async def test_compact_quota_exceeded_transparent_failover(async_client, monkeypatch):
    """quota_exceeded on A should fail over to B before response write."""
    await _import_account(async_client, "acc_compact_quota_a", "compactquotaa@example.com")
    await _import_account(async_client, "acc_compact_quota_b", "compactquotab@example.com")

    seen_account_ids: list[str | None] = []

    async def fake_compact(payload, headers, access_token, account_id):
        seen_account_ids.append(account_id)
        if account_id == "acc_compact_quota_a":
            raise ProxyResponseError(
                429,
                openai_error("quota_exceeded", "quota exceeded"),
                failure_phase="status",
            )
        return CompactResponsePayload.model_validate({"object": "response.compaction", "output": []})

    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": []}
    response = await async_client.post("/backend-api/codex/responses/compact", json=payload)
    assert response.status_code == 200
    assert response.json()["object"] == "response.compaction"
    assert seen_account_ids[:2] == ["acc_compact_quota_a", "acc_compact_quota_b"]

    async with SessionLocal() as session:
        account_id = generate_unique_account_id("acc_compact_quota_a", "compactquotaa@example.com")
        account_a = await session.get(Account, account_id)
        assert account_a is not None
        await session.refresh(account_a)
        assert account_a.status == AccountStatus.QUOTA_EXCEEDED


@pytest.mark.asyncio
async def test_compact_500_all_accounts_exhausted(async_client, monkeypatch):
    """500 on all accounts → error returned to client."""
    await _import_account(async_client, "acc_call_a", "call_a@example.com")

    async def fake_compact(payload, headers, access_token, account_id):
        raise ProxyResponseError(
            500,
            openai_error("server_error", "persistent error"),
            failure_phase="status",
            retryable_same_contract=True,
        )

    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": []}
    response = await async_client.post("/backend-api/codex/responses/compact", json=payload)
    # After exhausting all accounts, the load balancer returns 503 no_accounts
    assert response.status_code in (500, 503)


@pytest.mark.asyncio
async def test_compact_non_500_error_not_retried_as_transient(async_client, monkeypatch):
    """A 400 error should NOT be retried via the transient retry path."""
    await _import_account(async_client, "acc_c400", "c400@example.com")

    call_count = 0

    async def fake_compact(payload, headers, access_token, account_id):
        nonlocal call_count
        call_count += 1
        raise ProxyResponseError(
            400,
            openai_error("invalid_request_error", "bad request"),
            failure_phase="status",
        )

    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": []}
    response = await async_client.post("/backend-api/codex/responses/compact", json=payload)
    assert response.status_code == 400

    # Should NOT retry — only 1 call
    assert call_count == 1


@pytest.mark.asyncio
async def test_compact_502_still_uses_safe_retry_budget(async_client, monkeypatch):
    """502 errors should still use the existing safe_retry_budget (not transient path)."""
    await _import_account(async_client, "acc_c502", "c502@example.com")

    call_count = 0
    seen_account_ids: list[str | None] = []

    async def fake_compact(payload, headers, access_token, account_id):
        nonlocal call_count
        call_count += 1
        seen_account_ids.append(account_id)
        if call_count == 1:
            raise ProxyResponseError(
                502,
                openai_error("upstream_error", "bad gateway"),
                failure_phase="status",
                retryable_same_contract=True,
            )
        return CompactResponsePayload.model_validate({"object": "response.compaction", "output": []})

    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": []}
    response = await async_client.post("/backend-api/codex/responses/compact", json=payload)
    assert response.status_code == 200

    # safe_retry_budget=1 → retried once, same account
    assert call_count == 2
    assert seen_account_ids[0] == seen_account_ids[1]


@pytest.mark.asyncio
async def test_compact_sticky_503_unknown_code_excludes_failing_account_on_failover(async_client, monkeypatch):
    await _import_account(async_client, "acc_sticky_503_a", "sticky503a@example.com")
    await _import_account(async_client, "acc_sticky_503_b", "sticky503b@example.com")

    seen_account_ids: list[str | None] = []

    async def fake_compact(payload, headers, access_token, account_id):
        seen_account_ids.append(account_id)
        if account_id == "acc_sticky_503_a":
            raise ProxyResponseError(
                503,
                openai_error("bad_gateway", "Bad gateway"),
                failure_phase="status",
            )
        return CompactResponsePayload.model_validate({"object": "response.compaction", "output": []})

    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": []}
    response = await async_client.post(
        "/backend-api/codex/responses/compact",
        json=payload,
        headers={"x-codex-session-id": "sticky-session-503"},
    )
    assert response.status_code == 200
    assert response.json()["object"] == "response.compaction"
    assert seen_account_ids[:2] == ["acc_sticky_503_a", "acc_sticky_503_b"]


# ===========================================================================
# Failure classification: workspace deactivation, code-less usage limits,
# model capacity, and model-scoped rejections
# ===========================================================================


async def _import_accounts(async_client, *slugs: str) -> dict[str | None, str]:
    """Import accounts and map each upstream ``chatgpt_account_id`` to its internal id."""
    return {slug: await _import_account(async_client, slug, f"{slug}@example.test") for slug in slugs}


async def _account_status(account_id: str) -> tuple[AccountStatus, str | None]:
    async with SessionLocal() as session:
        account = await session.get(Account, account_id)
        assert account is not None
        return account.status, account.deactivation_reason


def _pin_file_owner(monkeypatch, owner_account_id: str) -> None:
    async def resolve_file_owner(self, payload, headers):
        del self, payload, headers
        return owner_account_id

    monkeypatch.setattr(proxy_module.ProxyService, "_resolve_file_account_for_responses", resolve_file_owner)


def _count_record_errors(monkeypatch) -> list[str]:
    recorded: list[str] = []
    original_record_errors = LoadBalancer.record_errors

    async def record_errors(self, account, count):
        recorded.extend([account.id] * count)
        return await original_record_errors(self, account, count)

    monkeypatch.setattr(LoadBalancer, "record_errors", record_errors)
    return recorded


_DEACTIVATED_WORKSPACE_ERROR = openai_error("deactivated_workspace", "Workspace has been deactivated")


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/v1/responses", "/backend-api/codex/responses"])
async def test_stream_deactivated_workspace_fails_over_and_excludes_only_that_workspace(
    async_client, monkeypatch, path: str
):
    accounts = await _import_accounts(async_client, "acc_workspace_a", "acc_workspace_b")
    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        if account_id == seen_account_ids[0]:
            raise ProxyResponseError(402, _DEACTIVATED_WORKSPACE_ERROR, failure_phase="status")
        yield _success_sse_event("resp_workspace_ok")

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)
    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}

    response = await async_client.post(path, json=payload)

    assert response.status_code == 200
    events = _extract_events(response.text.splitlines())
    assert [e["response"]["id"] for e in events if e.get("type") == "response.completed"] == ["resp_workspace_ok"]
    assert [e for e in events if e.get("type") == "response.failed"] == []
    unavailable, healthy = seen_account_ids
    assert unavailable != healthy

    second = await async_client.post(path, json=payload)
    assert second.status_code == 200
    assert seen_account_ids == [unavailable, healthy, healthy]
    assert await _account_status(accounts[unavailable]) == (AccountStatus.DEACTIVATED, "Workspace has been deactivated")
    assert await _account_status(accounts[healthy]) == (AccountStatus.ACTIVE, None)


async def _create_metered_proxy_key(async_client) -> tuple[str, str]:
    """A reserving key: its usage reservation is open until the request settles."""
    settings_response = await async_client.put("/api/settings", json={"apiKeyAuthEnabled": True})
    assert settings_response.status_code == 200
    created = await async_client.post(
        "/api/api-keys/",
        json={
            "name": "workspace-failover",
            "limits": [{"limitType": "total_tokens", "limitWindow": "weekly", "maxValue": 1_000_000}],
        },
    )
    assert created.status_code == 200
    return created.json()["id"], created.json()["key"]


def _assert_reservation_settled_before_permanent_failure(monkeypatch, key_id: str) -> list[str]:
    marked: list[str] = []
    original_mark = LoadBalancer.mark_permanent_failure

    async def mark_after_settlement(self, account, code):
        async with SessionLocal() as session:
            pending = await session.scalar(
                select(ApiKeyUsageReservation.id).where(
                    ApiKeyUsageReservation.api_key_id == key_id,
                    ApiKeyUsageReservation.status == "reserved",
                )
            )
        assert pending is None, "permanent health written while the API-key reservation was still open"
        marked.append(code)
        return await original_mark(self, account, code)

    monkeypatch.setattr(LoadBalancer, "mark_permanent_failure", mark_after_settlement)
    return marked


@pytest.mark.asyncio
async def test_stream_deactivated_workspace_settles_api_key_reservation_before_health_write(async_client, monkeypatch):
    accounts = await _import_accounts(async_client, "acc_workspace_keyed_a", "acc_workspace_keyed_b")
    key_id, key = await _create_metered_proxy_key(async_client)
    marked = _assert_reservation_settled_before_permanent_failure(monkeypatch, key_id)
    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        if account_id == seen_account_ids[0]:
            raise ProxyResponseError(402, _DEACTIVATED_WORKSPACE_ERROR, failure_phase="status")
        yield _success_sse_event("resp_workspace_keyed_ok")

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    response = await async_client.post(
        "/v1/responses",
        json={"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True},
        headers={"authorization": f"Bearer {key}"},
    )

    assert response.status_code == 200
    unavailable, healthy = seen_account_ids
    assert marked == ["deactivated_workspace"]
    assert (await _account_status(accounts[unavailable]))[0] == AccountStatus.DEACTIVATED
    assert (await _account_status(accounts[healthy]))[0] == AccountStatus.ACTIVE


@pytest.mark.asyncio
async def test_compact_deactivated_workspace_settles_api_key_reservation_before_health_write(async_client, monkeypatch):
    accounts = await _import_accounts(async_client, "acc_workspace_ckeyed_a", "acc_workspace_ckeyed_b")
    key_id, key = await _create_metered_proxy_key(async_client)
    marked = _assert_reservation_settled_before_permanent_failure(monkeypatch, key_id)
    seen_account_ids: list[str | None] = []

    async def fake_compact(payload, headers, access_token, account_id):
        seen_account_ids.append(account_id)
        if account_id == seen_account_ids[0]:
            raise ProxyResponseError(402, _DEACTIVATED_WORKSPACE_ERROR, failure_phase="status")
        return CompactResponsePayload.model_validate({"object": "response.compaction", "output": []})

    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)

    response = await async_client.post(
        "/backend-api/codex/responses/compact",
        json={"model": "gpt-5.1", "instructions": "hi", "input": []},
        headers={"authorization": f"Bearer {key}"},
    )

    assert response.status_code == 200
    unavailable, healthy = seen_account_ids
    assert marked == ["deactivated_workspace"]
    assert (await _account_status(accounts[unavailable]))[0] == AccountStatus.DEACTIVATED
    assert (await _account_status(accounts[healthy]))[0] == AccountStatus.ACTIVE


@pytest.mark.asyncio
async def test_stream_deactivated_workspace_does_not_move_a_file_pinned_request(async_client, monkeypatch):
    accounts = await _import_accounts(async_client, "acc_workspace_pin_a", "acc_workspace_pin_b")
    _pin_file_owner(monkeypatch, accounts["acc_workspace_pin_a"])
    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        if account_id == "acc_workspace_pin_a":
            raise ProxyResponseError(402, _DEACTIVATED_WORKSPACE_ERROR, failure_phase="status")
        yield _success_sse_event("resp_workspace_pin_wrong_owner")

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)
    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}

    response = await async_client.post("/backend-api/codex/responses", json=payload)

    assert seen_account_ids == ["acc_workspace_pin_a"]
    events = _extract_events(response.text.splitlines()) if response.status_code == 200 else []
    assert [e for e in events if e.get("type") == "response.completed"] == []
    assert (await _account_status(accounts["acc_workspace_pin_a"]))[0] == AccountStatus.DEACTIVATED
    assert await _account_status(accounts["acc_workspace_pin_b"]) == (AccountStatus.ACTIVE, None)


@pytest.mark.asyncio
async def test_stream_bare_402_does_not_deactivate_account(async_client, monkeypatch):
    accounts = await _import_accounts(async_client, "acc_payment")

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        raise ProxyResponseError(402, openai_error("payment_required", "Payment Required"), failure_phase="status")
        yield ""  # pragma: no cover

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    response = await async_client.post("/v1/responses", json={"model": "gpt-5.1", "input": "hi", "stream": True})

    assert response.status_code == 402
    assert response.json()["error"]["code"] == "payment_required"
    assert await _account_status(accounts["acc_payment"]) == (AccountStatus.ACTIVE, None)


@pytest.mark.asyncio
async def test_compact_deactivated_workspace_fails_over_once(async_client, monkeypatch):
    accounts = await _import_accounts(async_client, "acc_workspace_compact_a", "acc_workspace_compact_b")
    seen_account_ids: list[str | None] = []

    async def fake_compact(payload, headers, access_token, account_id):
        seen_account_ids.append(account_id)
        if account_id == seen_account_ids[0]:
            raise ProxyResponseError(402, _DEACTIVATED_WORKSPACE_ERROR, failure_phase="status")
        return CompactResponsePayload.model_validate({"object": "response.compaction", "output": []})

    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)

    response = await async_client.post(
        "/backend-api/codex/responses/compact",
        json={"model": "gpt-5.1", "instructions": "hi", "input": []},
    )

    assert response.status_code == 200
    assert response.json()["object"] == "response.compaction"
    unavailable, healthy = seen_account_ids
    assert unavailable != healthy
    assert await _account_status(accounts[unavailable]) == (AccountStatus.DEACTIVATED, "Workspace has been deactivated")
    assert await _account_status(accounts[healthy]) == (AccountStatus.ACTIVE, None)


_CODELESS_USAGE_LIMIT_FRAME_ERRORS = (
    {"message": "The usage limit has been reached"},
    {"message": "You've hit your usage limit."},
)
_USAGE_LIMIT_FRAME_ERRORS = (
    *_CODELESS_USAGE_LIMIT_FRAME_ERRORS,
    {"code": "usage_limit_reached", "message": "The usage limit has been reached"},
)


@pytest.mark.asyncio
@pytest.mark.parametrize("frame_error", _CODELESS_USAGE_LIMIT_FRAME_ERRORS)
async def test_stream_codeless_usage_limit_frame_walks_the_pool_and_benches_the_account(
    async_client, monkeypatch, frame_error
):
    accounts = await _import_accounts(async_client, "acc_frame_limit_a", "acc_frame_limit_b")
    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        if account_id == seen_account_ids[0]:
            yield _sse_event({"type": "response.failed", "response": {"error": frame_error}})
            return
        yield _success_sse_event("resp_frame_limit_ok")

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    assert [e for e in events if e.get("type") == "response.failed"] == []
    assert len([e for e in events if e.get("type") == "response.completed"]) == 1
    exhausted, serving = seen_account_ids[:2]
    assert exhausted != serving
    assert (await _account_status(accounts[exhausted]))[0] == AccountStatus.RATE_LIMITED


@pytest.mark.asyncio
@pytest.mark.parametrize("frame_error", _USAGE_LIMIT_FRAME_ERRORS)
async def test_stream_usage_limit_frame_on_the_last_account_still_benches_it(async_client, monkeypatch, frame_error):
    accounts = await _import_accounts(async_client, "acc_last_limit_a", "acc_last_limit_b", "acc_last_limit_c")

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        yield _sse_event({"type": "response.failed", "response": {"error": frame_error}})

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        [line async for line in resp.aiter_lines() if line]

    for account_id in accounts.values():
        assert (await _account_status(account_id))[0] == AccountStatus.RATE_LIMITED


@pytest.mark.asyncio
@pytest.mark.parametrize("frame_error", _USAGE_LIMIT_FRAME_ERRORS)
async def test_stream_usage_limit_frame_after_a_visible_event_still_benches_the_account(
    async_client, monkeypatch, frame_error
):
    accounts = await _import_accounts(async_client, "acc_visible_limit")

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        yield _sse_event({"type": "response.created", "response": {"id": "resp_visible_limit"}})
        yield _sse_event({"type": "response.failed", "response": {"error": frame_error}})

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    assert len([e for e in _extract_events(lines) if e.get("type") == "response.failed"]) == 1
    assert (await _account_status(accounts["acc_visible_limit"]))[0] == AccountStatus.RATE_LIMITED


@pytest.mark.asyncio
async def test_stream_codeless_rejection_echoing_usage_limit_with_request_code_is_not_benched(
    async_client, monkeypatch
):
    """Only the code-less form may be read off its message: a request-shaped 400 can echo the sentence."""
    accounts = await _import_accounts(async_client, "acc_echo_limit")

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        yield _sse_event(
            {
                "type": "response.failed",
                "response": {
                    "error": {"code": "invalid_request_error", "message": "Input mentions: usage limit reached"}
                },
            }
        )

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        [line async for line in resp.aiter_lines() if line]

    assert (await _account_status(accounts["acc_echo_limit"]))[0] == AccountStatus.ACTIVE


_MODEL_CAPACITY_ERROR = openai_error(
    "invalid_request_error",
    "Selected model is at capacity. Please try a different model.",
)


@pytest.mark.asyncio
async def test_stream_model_capacity_rejection_keeps_the_account_selectable(async_client, monkeypatch):
    """Capacity describes the requested model, so it must not spend the only account in the walk."""
    await _import_accounts(async_client, "acc_capacity_only")
    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        if len(seen_account_ids) == 1:
            raise ProxyResponseError(400, _MODEL_CAPACITY_ERROR, failure_phase="status")
        yield _success_sse_event("resp_capacity_cleared")

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    assert [e["response"]["id"] for e in events if e.get("type") == "response.completed"] == ["resp_capacity_cleared"]
    assert seen_account_ids == ["acc_capacity_only", "acc_capacity_only"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "expected_dispatches", "completed"),
    [
        (_MODEL_CAPACITY_ERROR, 7, True),
        (openai_error("server_error", "An error occurred while processing your request."), 6, False),
    ],
    ids=["capacity", "ordinary"],
)
async def test_stream_500_walk_returns_to_an_account_only_for_model_capacity(
    async_client, monkeypatch, body, expected_dispatches: int, completed: bool
):
    await _import_accounts(async_client, "acc_capacity_walk_a", "acc_capacity_walk_b")
    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        if len(seen_account_ids) <= 6:
            raise ProxyResponseError(500, body, failure_phase="status")
        yield _success_sse_event("resp_capacity_walk_ok")

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    assert len(seen_account_ids) == expected_dispatches
    assert set(seen_account_ids) == {"acc_capacity_walk_a", "acc_capacity_walk_b"}
    assert bool([e for e in events if e.get("type") == "response.completed"]) is completed


@pytest.mark.asyncio
async def test_compact_model_capacity_rejection_keeps_the_only_account_in_the_walk(async_client, monkeypatch):
    await _import_accounts(async_client, "acc_compact_capacity_only")
    seen_account_ids: list[str | None] = []

    async def fake_compact(payload, headers, access_token, account_id):
        seen_account_ids.append(account_id)
        if len(seen_account_ids) == 1:
            raise ProxyResponseError(400, _MODEL_CAPACITY_ERROR, failure_phase="status")
        return CompactResponsePayload.model_validate({"object": "response.compaction", "output": []})

    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)

    response = await async_client.post(
        "/backend-api/codex/responses/compact",
        json={"model": "gpt-5.1", "instructions": "hi", "input": []},
    )

    assert response.status_code == 200
    assert seen_account_ids == ["acc_compact_capacity_only", "acc_compact_capacity_only"]


_MODEL_NOT_FOUND_ERROR = openai_error(
    "model_not_found",
    "The model `gpt-5.1` does not exist or you do not have access to it.",
)


@pytest.mark.asyncio
async def test_stream_model_not_found_fails_over_without_account_health_penalty(async_client, monkeypatch):
    accounts = await _import_accounts(async_client, "acc_model_missing_a", "acc_model_missing_b")
    recorded_errors = _count_record_errors(monkeypatch)
    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        if account_id == seen_account_ids[0]:
            raise ProxyResponseError(404, _MODEL_NOT_FOUND_ERROR, failure_phase="status")
        yield _success_sse_event("resp_model_found")

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True}
    async with async_client.stream("POST", "/backend-api/codex/responses", json=payload) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines() if line]

    events = _extract_events(lines)
    assert [e["response"]["id"] for e in events if e.get("type") == "response.completed"] == ["resp_model_found"]
    rejected, serving = seen_account_ids
    assert rejected != serving
    assert recorded_errors == []
    assert await _account_status(accounts[rejected]) == (AccountStatus.ACTIVE, None)


@pytest.mark.asyncio
async def test_stream_model_not_found_keeps_a_file_pinned_request_on_its_owner(async_client, monkeypatch):
    accounts = await _import_accounts(async_client, "acc_model_missing_pin_a", "acc_model_missing_pin_b")
    _pin_file_owner(monkeypatch, accounts["acc_model_missing_pin_a"])
    recorded_errors = _count_record_errors(monkeypatch)
    seen_account_ids: list[str | None] = []

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        seen_account_ids.append(account_id)
        raise ProxyResponseError(404, _MODEL_NOT_FOUND_ERROR, failure_phase="status")
        yield ""  # pragma: no cover

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    response = await async_client.post(
        "/v1/responses",
        json={"model": "gpt-5.1", "instructions": "hi", "input": [], "stream": True},
    )

    assert seen_account_ids == ["acc_model_missing_pin_a"]
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"
    assert recorded_errors == []


@pytest.mark.asyncio
async def test_compact_model_not_found_surfaces_without_account_health_penalty(async_client, monkeypatch):
    accounts = await _import_accounts(async_client, "acc_compact_model_missing")
    recorded_errors = _count_record_errors(monkeypatch)

    async def fake_compact(payload, headers, access_token, account_id):
        raise ProxyResponseError(404, _MODEL_NOT_FOUND_ERROR, failure_phase="status")

    monkeypatch.setattr(proxy_module, "core_compact_responses", fake_compact)

    response = await async_client.post(
        "/backend-api/codex/responses/compact",
        json={"model": "gpt-5.1", "instructions": "hi", "input": []},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"
    assert recorded_errors == []
    assert await _account_status(accounts["acc_compact_model_missing"]) == (AccountStatus.ACTIVE, None)
