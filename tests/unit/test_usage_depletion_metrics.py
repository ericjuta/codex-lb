from __future__ import annotations

import time
from dataclasses import dataclass

import pytest

from app.core.usage import refresh_scheduler as refresh_scheduler_module
from app.modules.proxy._service.streaming import helpers as streaming_helpers_module

pytestmark = pytest.mark.unit


class _FakeChild:
    def __init__(self) -> None:
        self.value = 0.0

    def set(self, value: float) -> None:
        self.value = value

    def inc(self, amount: float = 1.0) -> None:
        self.value += amount


class _FakeMetric:
    def __init__(self) -> None:
        self.samples: dict[tuple[tuple[str, str], ...], _FakeChild] = {}

    def labels(self, **labels: str) -> _FakeChild:
        key = tuple(sorted(labels.items()))
        return self.samples.setdefault(key, _FakeChild())

    def value_for(self, **labels: str) -> float:
        key = tuple(sorted(labels.items()))
        child = self.samples.get(key)
        return child.value if child is not None else 0.0


@dataclass
class _UsageRow:
    used_percent: float | None
    reset_at: int | None


def test_publish_usage_gauges_sets_percent_and_reset_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    percent_gauge = _FakeMetric()
    reset_gauge = _FakeMetric()
    monkeypatch.setattr(refresh_scheduler_module, "PROMETHEUS_AVAILABLE", True)
    monkeypatch.setattr(refresh_scheduler_module, "account_usage_percent", percent_gauge)
    monkeypatch.setattr(refresh_scheduler_module, "account_usage_reset_seconds", reset_gauge)

    reset_at = int(time.time()) + 3600
    refresh_scheduler_module.publish_usage_gauges(
        {
            "primary": {"acct-1": _UsageRow(used_percent=47.0, reset_at=reset_at)},
            "secondary": {"acct-1": _UsageRow(used_percent=12.5, reset_at=None)},
        }
    )

    assert percent_gauge.value_for(account_id="acct-1", window="primary") == 47.0
    assert percent_gauge.value_for(account_id="acct-1", window="secondary") == 12.5
    reset_seconds = reset_gauge.value_for(account_id="acct-1", window="primary")
    assert 3590 < reset_seconds <= 3600
    assert reset_gauge.value_for(account_id="acct-1", window="secondary") == 0.0


def test_publish_usage_gauges_skips_missing_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    percent_gauge = _FakeMetric()
    reset_gauge = _FakeMetric()
    monkeypatch.setattr(refresh_scheduler_module, "PROMETHEUS_AVAILABLE", True)
    monkeypatch.setattr(refresh_scheduler_module, "account_usage_percent", percent_gauge)
    monkeypatch.setattr(refresh_scheduler_module, "account_usage_reset_seconds", reset_gauge)

    refresh_scheduler_module.publish_usage_gauges(
        {"primary": {"acct-1": None, "acct-2": _UsageRow(used_percent=None, reset_at=None)}}
    )

    assert percent_gauge.samples == {}
    assert reset_gauge.samples == {}


def test_publish_usage_gauges_reset_in_past_clamps_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    percent_gauge = _FakeMetric()
    reset_gauge = _FakeMetric()
    monkeypatch.setattr(refresh_scheduler_module, "PROMETHEUS_AVAILABLE", True)
    monkeypatch.setattr(refresh_scheduler_module, "account_usage_percent", percent_gauge)
    monkeypatch.setattr(refresh_scheduler_module, "account_usage_reset_seconds", reset_gauge)

    refresh_scheduler_module.publish_usage_gauges(
        {"primary": {"acct-1": _UsageRow(used_percent=99.0, reset_at=int(time.time()) - 100)}}
    )

    assert reset_gauge.value_for(account_id="acct-1", window="primary") == 0.0


def test_transient_error_metric_increments_by_code(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = _FakeMetric()
    monkeypatch.setattr(streaming_helpers_module, "PROMETHEUS_AVAILABLE", True)
    monkeypatch.setattr(streaming_helpers_module, "account_transient_errors_total", counter)

    streaming_helpers_module._record_transient_error_metric("upstream_websocket_open_timeout")
    streaming_helpers_module._record_transient_error_metric("upstream_websocket_open_timeout")
    streaming_helpers_module._record_transient_error_metric(None)

    assert counter.value_for(code="upstream_websocket_open_timeout") == 2.0
    assert counter.value_for(code="unknown") == 1.0
