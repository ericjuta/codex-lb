"""Regression tests: the keep-alive timer must not outlive a lost connection.

Stock uvicorn cancels the keep-alive ``TimerHandle`` in ``connection_lost``
only when ``exc is None``. After an RST / ``ConnectionResetError`` the armed
handle pins the protocol graph for ``--timeout-keep-alive`` seconds while
connection accounting already reports the connection gone.
"""

from __future__ import annotations

import asyncio
import builtins
import errno
import gc
import socket
import struct
import sys
import weakref
from typing import Any

import pytest
import uvicorn
from uvicorn.protocols.http.h11_impl import H11Protocol
from uvicorn.server import ServerState

from app.core.http_protocol import KeepAliveH11Protocol, load_http_protocol_class

pytestmark = pytest.mark.integration

_IDLE_WINDOW_SECONDS = 7200
_REQUEST = b"GET /echo HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"


def _app_protocols() -> list[type[Any]]:
    protocols: list[type[Any]] = [KeepAliveH11Protocol]
    try:
        from app.core.http_protocol_httptools import KeepAliveHttpToolsProtocol
    except ImportError:
        return protocols
    return [KeepAliveHttpToolsProtocol, KeepAliveH11Protocol]


_APP_PROTOCOLS = _app_protocols()


def _stock_protocols() -> list[type[Any]]:
    protocols: list[type[Any]] = [H11Protocol]
    try:
        from uvicorn.protocols.http.httptools_impl import HttpToolsProtocol
    except ImportError:
        return protocols
    return [HttpToolsProtocol, H11Protocol]


_STOCK_PROTOCOLS = _stock_protocols()


async def _echo_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    if scope["type"] != "http":
        raise AssertionError(scope["type"])
    while True:
        message = await receive()
        if not message.get("more_body", False):
            break
    body = b"ok"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


class _FakeTransport(asyncio.Transport):
    def __init__(self) -> None:
        super().__init__()
        self.buffer = bytearray()
        self.closed = False
        self.protocol: asyncio.BaseProtocol | None = None

    def write(self, data: bytes | bytearray | memoryview) -> None:
        self.buffer.extend(data)

    def is_closing(self) -> bool:
        return self.closed

    def close(self) -> None:
        self.closed = True

    def abort(self) -> None:
        self.closed = True

    def pause_reading(self) -> None:
        pass

    def resume_reading(self) -> None:
        pass

    def set_protocol(self, protocol: asyncio.BaseProtocol) -> None:
        self.protocol = protocol

    def get_extra_info(self, name: str, default: Any = None) -> Any:
        if name == "sockname":
            return ("127.0.0.1", 2455)
        if name == "peername":
            return ("127.0.0.1", 54321)
        return default


def _make_protocol(protocol_class: type[Any], **config_kwargs: Any) -> tuple[Any, _FakeTransport]:
    config = uvicorn.Config(app=_echo_app, lifespan="off", **config_kwargs)
    config.load()
    protocol = protocol_class(config=config, server_state=ServerState(), app_state={})
    transport = _FakeTransport()
    protocol.connection_made(transport)
    return protocol, transport


async def _wait_for_response(transport: _FakeTransport, timeout: float = 5.0) -> bytes:
    async with asyncio.timeout(timeout):
        while b"\r\n\r\n" not in transport.buffer or not bytes(transport.buffer).split(b"\r\n\r\n", 1)[1]:
            await asyncio.sleep(0.01)
    return bytes(transport.buffer)


def _peer_reset() -> ConnectionResetError:
    return ConnectionResetError(errno.ECONNRESET, "Connection reset by peer")


async def _complete_one_request(protocol_class: type[Any]) -> tuple[Any, Any]:
    protocol, transport = _make_protocol(protocol_class, timeout_keep_alive=_IDLE_WINDOW_SECONDS)
    protocol.data_received(_REQUEST)
    await _wait_for_response(transport)
    async with asyncio.timeout(5.0):
        while protocol.tasks:
            await asyncio.sleep(0)
    timer = protocol.timeout_keep_alive_task
    assert timer is not None and not timer.cancelled()
    return protocol, transport


@pytest.mark.parametrize("protocol_class", _APP_PROTOCOLS)
async def test_error_close_releases_keepalive_timer_and_protocol(protocol_class: type[Any]) -> None:
    protocol, transport = await _complete_one_request(protocol_class)
    timer = protocol.timeout_keep_alive_task
    ref = weakref.ref(protocol)

    protocol.connection_lost(_peer_reset())

    assert protocol not in protocol.connections
    assert protocol.timeout_keep_alive_task is None
    assert timer.cancelled()
    assert transport.closed is False
    del protocol, transport
    gc.collect()
    assert ref() is None


@pytest.mark.parametrize("protocol_class", _APP_PROTOCOLS)
async def test_clean_close_behavior_is_unchanged(protocol_class: type[Any]) -> None:
    protocol, transport = await _complete_one_request(protocol_class)
    ref = weakref.ref(protocol)

    protocol.connection_lost(None)

    assert transport.closed is True
    assert protocol.timeout_keep_alive_task is None
    del protocol, transport
    gc.collect()
    assert ref() is None


@pytest.mark.parametrize("protocol_class", _APP_PROTOCOLS)
async def test_keepalive_timer_still_closes_an_idle_connection(protocol_class: type[Any]) -> None:
    protocol, transport = await _complete_one_request(protocol_class)
    protocol.timeout_keep_alive_task.cancel()

    protocol.timeout_keep_alive_handler()

    assert transport.closed is True


@pytest.mark.parametrize("protocol_class", _APP_PROTOCOLS)
async def test_error_close_during_request_leaves_cycle_disconnected(protocol_class: type[Any]) -> None:
    protocol, transport = _make_protocol(protocol_class, timeout_keep_alive=_IDLE_WINDOW_SECONDS)
    head = b"POST /echo HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 2\r\n\r\n"
    protocol.data_received(head)
    await asyncio.sleep(0.01)
    assert protocol.cycle is not None and not protocol.cycle.response_complete

    protocol.connection_lost(_peer_reset())

    assert protocol.cycle.disconnected is True
    assert protocol.timeout_keep_alive_task is None
    async with asyncio.timeout(5.0):
        while protocol.tasks:
            await asyncio.sleep(0)
    assert transport.closed is False


def _reset_after_one_request(port: int) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=5.0) as client:
        client.sendall(_REQUEST)
        buffer = b""
        while b"\r\n\r\n" not in buffer or not buffer.split(b"\r\n\r\n", 1)[1]:
            chunk = client.recv(65536)
            if not chunk:
                raise AssertionError(f"server closed before responding: {buffer!r}")
            buffer += chunk
        client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        return buffer


async def _exercise_live_server_peer_reset(protocol_class: type[Any], *, connections: int = 1) -> None:
    config = uvicorn.Config(app=_echo_app, lifespan="off", timeout_keep_alive=_IDLE_WINDOW_SECONDS)
    config.load()
    state = ServerState()
    refs: list[weakref.ref[Any]] = []
    lost_with: list[BaseException | None] = []
    timer_cleanup: list[tuple[bool, bool]] = []

    class _Recording(protocol_class):  # type: ignore[misc, valid-type]
        def connection_lost(self, exc: Exception | None) -> None:
            timer = self.timeout_keep_alive_task
            super().connection_lost(exc)
            lost_with.append(exc)
            timer_cleanup.append((self.timeout_keep_alive_task is None, timer is not None and timer.cancelled()))

    def factory() -> Any:
        protocol = _Recording(config=config, server_state=state, app_state={})
        refs.append(weakref.ref(protocol))
        return protocol

    server = await asyncio.get_running_loop().create_server(factory, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        responses = [await asyncio.to_thread(_reset_after_one_request, port) for _ in range(connections)]
        async with asyncio.timeout(10.0):
            while len(lost_with) < connections:
                await asyncio.sleep(0.01)
    finally:
        server.close()
        await server.wait_closed()

    assert len(responses) == connections
    for response in responses:
        response_head, response_body = response.split(b"\r\n\r\n", 1)
        assert response_head.splitlines()[0] == b"HTTP/1.1 200 OK"
        assert response_body == b"ok"
    assert len(refs) == connections
    assert all(isinstance(exc, ConnectionResetError) for exc in lost_with), lost_with
    assert timer_cleanup == [(True, True)] * connections
    assert not state.connections
    gc.collect()
    assert [ref() for ref in refs] == [None] * connections


async def test_live_server_releases_protocol_after_peer_reset() -> None:
    await _exercise_live_server_peer_reset(load_http_protocol_class(), connections=5)


@pytest.mark.parametrize("http", ["h11", "httptools"])
async def test_explicit_protocol_selection_handles_peer_reset(http: str) -> None:
    try:
        protocol_class = load_http_protocol_class(http)
    except ImportError:
        if http == "httptools":
            pytest.skip("httptools is not installed")
        raise

    await _exercise_live_server_peer_reset(protocol_class)


async def test_auto_selection_handles_peer_reset_without_httptools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_name = "app.core.http_protocol_httptools"
    real_import = builtins.__import__
    monkeypatch.delitem(sys.modules, module_name, raising=False)

    def import_without_httptools(name: str, globals=None, locals=None, fromlist=(), level: int = 0):
        if name == module_name:
            raise ImportError("httptools unavailable")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", import_without_httptools)

    await _exercise_live_server_peer_reset(load_http_protocol_class("auto"))
    with pytest.raises(ImportError):
        load_http_protocol_class("httptools")


@pytest.mark.parametrize("protocol_class", _STOCK_PROTOCOLS)
async def test_stock_protocol_keeps_keepalive_timer_armed_after_error_close(protocol_class: type[Any]) -> None:
    protocol, transport = await _complete_one_request(protocol_class)
    timer = protocol.timeout_keep_alive_task
    ref = weakref.ref(protocol)
    try:
        protocol.connection_lost(_peer_reset())

        assert protocol not in protocol.connections
        assert protocol.timeout_keep_alive_task is timer and not timer.cancelled()
        del protocol, transport
        gc.collect()
        assert ref() is not None
    finally:
        timer.cancel()
