from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config.settings import Settings

pytestmark = pytest.mark.unit


def test_direct_websocket_liveness_settings_defaults() -> None:
    settings = Settings()

    assert settings.proxy_websocket_connect_attempt_timeout_seconds == 10.0
    assert settings.proxy_websocket_connect_budget_seconds == 20.0


def test_direct_websocket_liveness_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEX_LB_PROXY_WEBSOCKET_CONNECT_ATTEMPT_TIMEOUT_SECONDS", "4.5")
    monkeypatch.setenv("CODEX_LB_PROXY_WEBSOCKET_CONNECT_BUDGET_SECONDS", "13")

    settings = Settings()

    assert settings.proxy_websocket_connect_attempt_timeout_seconds == 4.5
    assert settings.proxy_websocket_connect_budget_seconds == 13.0


@pytest.mark.parametrize(
    ("attempt_timeout_seconds", "connect_budget_seconds"),
    [
        (0.0, 20.0),
        (10.0, 0.0),
    ],
)
def test_direct_websocket_liveness_settings_require_positive_values(
    attempt_timeout_seconds: float,
    connect_budget_seconds: float,
) -> None:
    with pytest.raises(ValidationError):
        Settings(
            proxy_websocket_connect_attempt_timeout_seconds=attempt_timeout_seconds,
            proxy_websocket_connect_budget_seconds=connect_budget_seconds,
        )
