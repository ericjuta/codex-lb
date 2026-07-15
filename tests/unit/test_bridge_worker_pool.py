from __future__ import annotations

import gzip

import aiohttp
import pytest
from aiohttp import web

from app.core.runtime.bridge_worker_pool import (
    BridgeWorkerConfig,
    _BridgeFrontProxy,
    _is_downstream_disconnect,
    build_worker_configs,
    build_worker_env,
)

pytestmark = pytest.mark.unit


def test_build_worker_configs_makes_unique_loopback_endpoints(monkeypatch):
    monkeypatch.delenv("CODEX_LB_BRIDGE_WORKER_BASE_PORT", raising=False)

    workers = build_worker_configs(worker_count=3, public_port=2455, instance_id_base="codex-lb")

    assert [worker.instance_id for worker in workers] == [
        "codex-lb-worker-1",
        "codex-lb-worker-2",
        "codex-lb-worker-3",
    ]
    assert [worker.port for worker in workers] == [3455, 3456, 3457]
    assert [worker.base_url for worker in workers] == [
        "http://127.0.0.1:3455",
        "http://127.0.0.1:3456",
        "http://127.0.0.1:3457",
    ]


def test_build_worker_configs_uses_explicit_base_port(monkeypatch):
    monkeypatch.setenv("CODEX_LB_BRIDGE_WORKER_BASE_PORT", "4500")

    workers = build_worker_configs(worker_count=2, public_port=2455, instance_id_base="bridge")

    assert [worker.port for worker in workers] == [4500, 4501]


def test_build_worker_configs_rejects_single_worker():
    with pytest.raises(ValueError, match="greater than one"):
        build_worker_configs(worker_count=1, public_port=2455, instance_id_base="bridge")


def test_build_worker_env_sets_addressable_bridge_owner():
    worker = build_worker_configs(worker_count=2, public_port=2455, instance_id_base="bridge")[0]

    env = build_worker_env(worker, base_env={"CODEX_LB_UVICORN_WORKERS": "8"})

    assert env["PORT"] == "3455"
    assert env["CODEX_LB_UVICORN_WORKERS"] == "1"
    assert env["UVICORN_WORKERS"] == "1"
    assert env["CODEX_LB_HTTP_RESPONSES_SESSION_BRIDGE_INSTANCE_ID"] == "bridge-worker-1"
    assert env["CODEX_LB_HTTP_RESPONSES_SESSION_BRIDGE_ADVERTISE_BASE_URL"] == "http://127.0.0.1:3455"


def test_build_worker_env_disables_shared_background_loops_for_followers():
    follower = build_worker_configs(worker_count=2, public_port=2455, instance_id_base="bridge")[1]

    env = build_worker_env(
        follower,
        base_env={
            "CODEX_LB_METRICS_ENABLED": "true",
            "CODEX_LB_MODEL_REGISTRY_ENABLED": "true",
            "CODEX_LB_STICKY_SESSION_CLEANUP_ENABLED": "true",
            "CODEX_LB_USAGE_REFRESH_ENABLED": "true",
        },
    )

    assert env["CODEX_LB_METRICS_ENABLED"] == "false"
    assert env["CODEX_LB_MODEL_REGISTRY_ENABLED"] == "true"
    assert env["CODEX_LB_STICKY_SESSION_CLEANUP_ENABLED"] == "false"
    assert env["CODEX_LB_USAGE_REFRESH_ENABLED"] == "false"


def test_downstream_disconnect_guard_classifies_benign_client_resets():
    assert _is_downstream_disconnect(aiohttp.ClientConnectionResetError("Cannot write to closing transport"))
    assert _is_downstream_disconnect(ConnectionResetError("connection reset by peer"))
    assert _is_downstream_disconnect(BrokenPipeError("broken pipe"))
    assert not _is_downstream_disconnect(RuntimeError("upstream failed"))


@pytest.mark.asyncio
async def test_front_proxy_forwards_gzip_response_body_verbatim(unused_tcp_port_factory):
    """Regression: auto-decompressing worker responses while forwarding the
    original Content-Encoding header corrupted dashboard asset bodies."""
    payload = b"const dashboard = 1;" * 200
    gzipped = gzip.compress(payload)

    async def asset(_: web.Request) -> web.Response:
        return web.Response(
            body=gzipped,
            headers={
                "Content-Type": "text/javascript",
                "Content-Encoding": "gzip",
                "Vary": "Accept-Encoding",
            },
        )

    worker_port = unused_tcp_port_factory()
    worker_app = web.Application()
    worker_app.router.add_get("/assets/index.js", asset)
    worker_runner = web.AppRunner(worker_app)
    await worker_runner.setup()
    await web.TCPSite(worker_runner, host="127.0.0.1", port=worker_port).start()

    proxy_port = unused_tcp_port_factory()
    proxy = _BridgeFrontProxy(
        (
            BridgeWorkerConfig(
                index=0,
                port=worker_port,
                instance_id="codex-lb-worker-1",
                base_url=f"http://127.0.0.1:{worker_port}",
            ),
        )
    )
    proxy_runner = await proxy.start(host="127.0.0.1", port=proxy_port, ssl_context=None)

    try:
        async with aiohttp.ClientSession(auto_decompress=False) as client:
            async with client.get(
                f"http://127.0.0.1:{proxy_port}/assets/index.js",
                headers={"Accept-Encoding": "gzip"},
            ) as response:
                body = await response.read()
                assert response.status == 200
                assert response.headers.get("Content-Encoding") == "gzip"
                assert body == gzipped
                assert gzip.decompress(body) == payload
    finally:
        await proxy_runner.cleanup()
        await worker_runner.cleanup()
