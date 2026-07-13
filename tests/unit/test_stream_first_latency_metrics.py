from __future__ import annotations

import pytest

from app.modules.proxy._service import request_log as request_log_module

pytestmark = pytest.mark.unit


class _FakeChild:
    def __init__(self) -> None:
        self.observations: list[float] = []

    def observe(self, value: float) -> None:
        self.observations.append(value)


class _FakeHistogram:
    def __init__(self) -> None:
        self.samples: dict[tuple[tuple[str, str], ...], _FakeChild] = {}

    def labels(self, **labels: str) -> _FakeChild:
        key = tuple(sorted(labels.items()))
        return self.samples.setdefault(key, _FakeChild())

    def observations_for(self, **labels: str) -> list[float]:
        key = tuple(sorted(labels.items()))
        child = self.samples.get(key)
        return child.observations if child is not None else []


@pytest.fixture
def histograms(monkeypatch: pytest.MonkeyPatch) -> tuple[_FakeHistogram, _FakeHistogram]:
    first_event = _FakeHistogram()
    first_token = _FakeHistogram()
    monkeypatch.setattr(request_log_module, "PROMETHEUS_AVAILABLE", True)
    monkeypatch.setattr(request_log_module, "stream_first_event_seconds", first_event)
    monkeypatch.setattr(request_log_module, "stream_first_token_seconds", first_token)
    return first_event, first_token


def test_first_event_observation_recorded(histograms: tuple[_FakeHistogram, _FakeHistogram]) -> None:
    first_event, first_token = histograms
    request_log_module._record_stream_first_latency(
        kind="first_event",
        elapsed_seconds=1.25,
        transport="websocket",
        model="gpt-5.6-luna",
    )
    assert first_event.observations_for(transport="websocket", model="gpt-5.6-luna") == [1.25]
    assert first_token.samples == {}


def test_first_token_observation_recorded(histograms: tuple[_FakeHistogram, _FakeHistogram]) -> None:
    first_event, first_token = histograms
    request_log_module._record_stream_first_latency(
        kind="first_token",
        elapsed_seconds=8.5,
        transport="http",
        model="gpt-5.6-terra",
    )
    assert first_token.observations_for(transport="http", model="gpt-5.6-terra") == [8.5]
    assert first_event.samples == {}


def test_unknown_labels_are_defaulted(histograms: tuple[_FakeHistogram, _FakeHistogram]) -> None:
    first_event, _ = histograms
    request_log_module._record_stream_first_latency(
        kind="first_event",
        elapsed_seconds=0.5,
        transport=None,
        model=None,
    )
    assert first_event.observations_for(transport="unknown", model="unknown") == [0.5]


def test_negative_elapsed_is_dropped(histograms: tuple[_FakeHistogram, _FakeHistogram]) -> None:
    first_event, first_token = histograms
    request_log_module._record_stream_first_latency(
        kind="first_event",
        elapsed_seconds=-0.1,
        transport="http",
        model="gpt-5.6-luna",
    )
    assert first_event.samples == {}


def test_noop_when_prometheus_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(request_log_module, "PROMETHEUS_AVAILABLE", False)
    monkeypatch.setattr(request_log_module, "stream_first_event_seconds", None)
    request_log_module._record_stream_first_latency(
        kind="first_event",
        elapsed_seconds=1.0,
        transport="http",
        model="gpt-5.6-luna",
    )
