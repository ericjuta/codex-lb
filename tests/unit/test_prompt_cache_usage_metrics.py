from __future__ import annotations

import pytest

from app.modules.proxy._service import request_log as request_log_module

pytestmark = pytest.mark.unit


class _FakeChild:
    def __init__(self) -> None:
        self.value = 0.0

    def inc(self, amount: float = 1.0) -> None:
        self.value += amount


class _FakeCounter:
    def __init__(self) -> None:
        self.samples: dict[tuple[tuple[str, str], ...], _FakeChild] = {}

    def labels(self, **labels: str) -> _FakeChild:
        key = tuple(sorted(labels.items()))
        return self.samples.setdefault(key, _FakeChild())

    def value_for(self, **labels: str) -> float:
        key = tuple(sorted(labels.items()))
        child = self.samples.get(key)
        return child.value if child is not None else 0.0


@pytest.fixture
def counters(monkeypatch: pytest.MonkeyPatch) -> tuple[_FakeCounter, _FakeCounter]:
    input_counter = _FakeCounter()
    cached_counter = _FakeCounter()
    monkeypatch.setattr(request_log_module, "PROMETHEUS_AVAILABLE", True)
    monkeypatch.setattr(request_log_module, "prompt_cache_input_tokens_total", input_counter)
    monkeypatch.setattr(request_log_module, "prompt_cache_cached_tokens_total", cached_counter)
    return input_counter, cached_counter


def test_records_input_and_cached_tokens(counters: tuple[_FakeCounter, _FakeCounter]) -> None:
    input_counter, cached_counter = counters
    request_log_module._record_prompt_cache_usage(
        model="gpt-5.6-luna",
        request_kind="normal",
        input_tokens=120_000,
        cached_input_tokens=30_000,
    )
    assert input_counter.value_for(model="gpt-5.6-luna", request_kind="normal") == 120_000
    assert cached_counter.value_for(model="gpt-5.6-luna", request_kind="normal") == 30_000


def test_zero_cached_tokens_only_updates_input(counters: tuple[_FakeCounter, _FakeCounter]) -> None:
    input_counter, cached_counter = counters
    request_log_module._record_prompt_cache_usage(
        model="gpt-5.6-luna",
        request_kind="prewarm",
        input_tokens=100,
        cached_input_tokens=0,
    )
    assert input_counter.value_for(model="gpt-5.6-luna", request_kind="prewarm") == 100
    assert cached_counter.samples == {}


def test_missing_usage_does_not_record(counters: tuple[_FakeCounter, _FakeCounter]) -> None:
    input_counter, cached_counter = counters
    request_log_module._record_prompt_cache_usage(
        model="gpt-5.6-luna",
        request_kind="normal",
        input_tokens=None,
        cached_input_tokens=None,
    )
    assert input_counter.samples == {}
    assert cached_counter.samples == {}


def test_unknown_model_label(counters: tuple[_FakeCounter, _FakeCounter]) -> None:
    input_counter, _ = counters
    request_log_module._record_prompt_cache_usage(
        model=None,
        request_kind="normal",
        input_tokens=10,
        cached_input_tokens=None,
    )
    assert input_counter.value_for(model="unknown", request_kind="normal") == 10
