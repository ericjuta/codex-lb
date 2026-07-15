from __future__ import annotations

import pytest

import app.core.balancer.logic as balancer_logic
from app.core.balancer import configure_replica_salt
from app.core.config.settings import Settings
from app.main import _bridge_replica_salt

pytestmark = pytest.mark.unit


def test_bridge_enabled_workers_preserve_configured_instance_identities() -> None:
    worker_one = Settings(
        http_responses_session_bridge_enabled=True,
        http_responses_session_bridge_instance_id="bridge-worker-1",
    )
    worker_two = Settings(
        http_responses_session_bridge_enabled=True,
        http_responses_session_bridge_instance_id="bridge-worker-2",
    )

    assert _bridge_replica_salt(worker_one) == "bridge-worker-1"
    assert _bridge_replica_salt(worker_two) == "bridge-worker-2"


def test_bridge_disabled_workers_use_stable_pid_qualified_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        http_responses_session_bridge_enabled=False,
        http_responses_session_bridge_instance_id="shared-host",
    )
    current_pid = {"value": 101}
    monkeypatch.setattr(balancer_logic.os, "getpid", lambda: current_pid["value"])
    monkeypatch.setattr(balancer_logic.socket, "gethostname", lambda: "shared-host")

    try:
        configure_replica_salt(_bridge_replica_salt(settings))
        worker_one_salt = balancer_logic._effective_replica_salt(None)
        assert balancer_logic._effective_replica_salt(None) == worker_one_salt

        current_pid["value"] = 202
        worker_two_salt = balancer_logic._effective_replica_salt(None)

        assert worker_one_salt == "shared-host:101"
        assert worker_two_salt == "shared-host:202"
        assert worker_two_salt != worker_one_salt
    finally:
        configure_replica_salt(None)
